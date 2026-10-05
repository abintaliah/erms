from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from psycopg import Connection, DataError, IntegrityError
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

from ..audit_context import actor_user_id_context
from ..authorization_policy import require_classifications_admin
from ..database import get_connection, pool
from .codec import MAX_BYTES, TransferError, decode, encode
from .service import export_package, import_package

router = APIRouter(
    prefix="/api/v1/classification-schemes",
    tags=["classification transfer"],
    dependencies=[Depends(require_classifications_admin)],
)


def transfer_error(error):
    status = {
        "duplicate_code": 409,
        "scheme_not_found": 404,
        "file_too_large": 413,
        "revision_unavailable": 503,
    }.get(error.code, 422)
    key = (
        error.code
        if error.code
        in {
            "invalid_package",
            "checksum_mismatch",
            "duplicate_code",
            "unsupported_language",
            "file_too_large",
            "revision_unavailable",
        }
        else "invalid_package"
    )
    return HTTPException(
        status,
        detail={
            "code": "classification_transfer." + error.code,
            "message_key": "classification_transfer.error." + key,
            "field": error.field,
        },
    )


@router.post("/import", status_code=201)
def import_scheme(
    format: Literal["json", "csv"] = Query(...),
    file: UploadFile = File(...),
    connection: Connection = Depends(get_connection, scope="function"),
):
    try:
        package = decode(file.file.read(MAX_BYTES + 1), format)
        with connection.transaction():
            return import_package(connection, package)
    except TransferError as exc:
        raise transfer_error(exc) from exc
    except IntegrityError as exc:
        code = "duplicate_code" if exc.sqlstate == "23505" else "invalid_package"
        raise transfer_error(TransferError(code)) from exc
    except (DataError, RaiseException) as exc:
        raise transfer_error(TransferError("invalid_package")) from exc


@router.get("/{scheme_id}/export")
def export_scheme(
    scheme_id: int,
    format: Literal["json", "csv", "docx"] = Query(...),
    language: str | None = None,
):
    try:
        with pool.connection() as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            package = export_package(
                connection, scheme_id, int(actor_user_id_context.get())
            )
            if format == "docx":
                from .word import render_word

                try:
                    content = render_word(connection, package, language)
                except TransferError:
                    raise
                except ValueError as exc:
                    # DOCX is XML-backed: fail explicitly for unrepresentable
                    # source characters instead of silently removing text.
                    raise TransferError("invalid_package", "document_text") from exc
                if len(content) > MAX_BYTES:
                    raise TransferError("file_too_large")
            else:
                content = encode(package, format)
        # Generation uses an unchanged repeatable-read snapshot. Audit in a
        # separate context-configured transaction and commit before responding.
        scheme = package["data"]["scheme"]
        metadata = {
            "export_id": package["manifest"]["export_id"],
            "format": format,
            "scheme": {"id": scheme_id, "code": scheme["code"], "title": scheme["title"]},
        }
        if format == "docx":
            metadata["language"] = language
        with contextmanager(get_connection)() as audit_connection:
            audit_connection.execute(
                """INSERT INTO event_history
                (entity_type,entity_id,operation,actor_user_id,actor_name,actor_email,
                 actor_type,source,request_id,correlation_id,metadata)
                VALUES ('classification_scheme',%s,'EXPORT',
                    NULLIF(current_setting('app.user_id',true),'')::bigint,
                    NULLIF(current_setting('app.actor_name',true),''),
                    NULLIF(current_setting('app.actor_email',true),''),
                    current_setting('app.actor_type',true),
                    current_setting('app.event_source',true),
                    NULLIF(current_setting('app.request_id',true),'')::uuid,
                    NULLIF(current_setting('app.correlation_id',true),'')::uuid,%s)""",
                (scheme_id, Jsonb(metadata)),
            )
        media = {
            "json": "application/json",
            "csv": "text/csv",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }[format]
        return Response(
            content,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="classification-scheme-{scheme_id}.{format}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except TransferError as exc:
        raise transfer_error(exc) from exc
