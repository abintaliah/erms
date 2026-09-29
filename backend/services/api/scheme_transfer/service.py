"""Database mapping for scheme transfer; all writes use the caller's transaction."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from .codec import MAX_BYTES, MAX_CLASSES, TransferError, ordered, seal, validate

ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=1)
def application_revision():
    value = os.environ.get("WATHIQ_APPLICATION_REVISION")
    if not value:
        try:
            value = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, timeout=5
            ).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise TransferError("revision_unavailable") from exc
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value):
        raise TransferError("revision_unavailable")
    return value


def timestamp(value):
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def exported(row):
    result = {}
    for key, value in row.items():
        if key in (
            "classification_scheme_id",
            "parent_classification_id",
            "classification_id",
        ):
            continue
        if key == "id":
            result["source_id"] = str(value)
        elif key == "version":
            result[key] = str(value)
        else:
            result[key] = timestamp(value) if isinstance(value, datetime) else value
    return result


def export_package(connection, scheme_id, actor_id):
    """Caller must establish REPEATABLE READ before the first snapshot query."""
    source = connection.execute(
        "SELECT * FROM classification_schemes WHERE id=%s", (scheme_id,)
    ).fetchone()
    if source is None:
        raise TransferError("scheme_not_found")
    size = connection.execute(
        """SELECT pg_column_size(s) +
        COALESCE((SELECT sum(pg_column_size(c)) FROM classifications c WHERE c.classification_scheme_id=s.id),0) +
        COALESCE((SELECT sum(pg_column_size(r)) FROM classification_retention_rules r JOIN classifications c ON c.id=r.classification_id WHERE c.classification_scheme_id=s.id),0) AS bytes
        FROM classification_schemes s WHERE s.id=%s""",
        (scheme_id,),
    ).fetchone()["bytes"]
    if size > MAX_BYTES:
        raise TransferError("file_too_large")
    scheme = exported(source)
    rows = connection.execute(
        'SELECT * FROM classifications WHERE classification_scheme_id=%s ORDER BY code COLLATE "C" LIMIT %s',
        (scheme_id, MAX_CLASSES + 1),
    ).fetchall()
    if len(rows) > MAX_CLASSES:
        raise TransferError("file_too_large")
    codes = {row["id"]: row["code"] for row in rows}
    rules = {
        row["classification_id"]: exported(row)
        for row in connection.execute(
            "SELECT rule.* FROM classification_retention_rules rule JOIN classifications c ON c.id=rule.classification_id WHERE c.classification_scheme_id=%s",
            (scheme_id,),
        )
    }
    scheme["classifications"] = ordered(
        [
            dict(
                exported(row),
                parent_code=codes.get(row["parent_classification_id"]),
                retention_rule=rules.get(row["id"]),
            )
            for row in rows
        ]
    )
    actor = connection.execute(
        "SELECT id,name,email FROM users WHERE id=%s", (actor_id,)
    ).fetchone()
    if not actor:
        raise TransferError("invalid_actor")
    migrations = [
        r["version"]
        for r in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ]
    # Fresh canonical installs deliberately have no migration ledger rows.
    schema_id = (
        "migrations:" + ",".join(migrations)
        if migrations
        else "canonical-sha256:"
        + hashlib.sha256((ROOT / "database/schema.sql").read_bytes()).hexdigest()
    )
    return seal(
        dict(
            package_type="classification_scheme_export",
            format_version="1.0",
            manifest=dict(
                export_id=str(uuid4()),
                exported_at=timestamp(datetime.now(timezone.utc)),
                exported_by=dict(
                    source_user_id=str(actor["id"]),
                    username=actor["email"],
                    display_name=actor["name"],
                ),
                source=dict(
                    application="Wathiq",
                    application_revision=application_revision(),
                    database_name=connection.execute(
                        "SELECT current_database() AS name"
                    ).fetchone()["name"],
                    schema_version=schema_id,
                ),
                counts=dict(classifications=len(rows), retention_rules=len(rules)),
            ),
            data={"scheme": scheme},
        )
    )


def import_package(connection, package):
    validate(package)
    scheme = package["data"]["scheme"]
    if connection.execute(
        "SELECT 1 FROM classification_schemes WHERE lower(code)=lower(%s)",
        (scheme["code"],),
    ).fetchone():
        raise TransferError("duplicate_code", scheme["code"])
    entities = [scheme, *scheme["classifications"]]
    languages = {lang for entity in entities for lang in (entity["translations"] or {})}
    enabled = {
        row["language_tag"]
        for row in connection.execute(
            "SELECT language_tag FROM supported_languages WHERE is_enabled"
        )
    }
    if languages - enabled:
        raise TransferError(
            "unsupported_language", ", ".join(sorted(languages - enabled))
        )
    # Let PostgreSQL apply its exact lower()/collation uniqueness semantics.
    codes = [item["code"] for item in scheme["classifications"]]
    duplicate = connection.execute(
        "SELECT lower(code) AS code FROM unnest(%s::text[]) AS code GROUP BY lower(code) HAVING count(*)>1 LIMIT 1",
        (codes,),
    ).fetchone()
    if duplicate:
        raise TransferError("duplicate_code", duplicate["code"])
    original_metadata = connection.execute(
        "SELECT current_setting('app.event_metadata',true) AS value"
    ).fetchone()["value"]
    base_metadata = json.loads(original_metadata or "{}")

    def insert(table, source, extra, kind):
        values = {
            k: v
            for k, v in source.items()
            if k
            not in ("source_id", "classifications", "parent_code", "retention_rule")
        }
        values.update(extra)
        if "translations" in values and values["translations"] is not None:
            values["translations"] = Jsonb(values["translations"])
        # CREATE after_state supplies the destination identity; source snapshot
        # plus manifest supplies the immutable source-to-local provenance map.
        metadata = dict(
            base_metadata,
            classification_scheme_import=dict(
                manifest=package["manifest"],
                source_entity_type=kind,
                source_entity={
                    k: v
                    for k, v in source.items()
                    if k not in ("classifications", "retention_rule")
                },
                source_scheme_id=scheme["source_id"],
                source_scheme_code=scheme["code"],
            ),
        )
        connection.execute(
            "SELECT set_config('app.event_metadata',%s,true)",
            (json.dumps(metadata, ensure_ascii=False),),
        )
        return connection.execute(
            sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.Placeholder() for _ in values),
            ),
            list(values.values()),
        ).fetchone()["id"]

    try:
        scheme_id = insert(
            "classification_schemes",
            scheme,
            {"date_published": None},
            "classification_scheme",
        )
        local_ids = {}
        for item in ordered(scheme["classifications"]):
            local_id = insert(
                "classifications",
                item,
                dict(
                    classification_scheme_id=scheme_id,
                    parent_classification_id=local_ids.get(item["parent_code"]),
                ),
                "classification",
            )
            local_ids[item["code"]] = local_id
            if item["retention_rule"]:
                insert(
                    "classification_retention_rules",
                    item["retention_rule"],
                    {"classification_id": local_id},
                    "classification_retention_rule",
                )
        connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
        return dict(id=scheme_id, code=scheme["code"], date_published=None)
    finally:
        # On SQL failure the transaction is aborted; its caller rolls it back.
        if connection.info.transaction_status.name != "INERROR":
            connection.execute(
                "SELECT set_config('app.event_metadata',%s,true)",
                (original_metadata or "{}",),
            )
