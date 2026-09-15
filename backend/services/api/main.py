from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from urllib.parse import quote
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg import Connection
from psycopg.types.json import Jsonb

from .audit_context import (
    actor_type_context,
    change_reason_context,
    correlation_id_context,
    event_source_context,
    request_id_context,
)
from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .concurrency import expected_version
from .content_storage import configured_storage, read_upload
from .database import close_pool, get_connection, open_pool
from .schemas import (
    AggregationCreate,
    AggregationRead,
    AggregationUpdate,
    DigitalComponentCreate,
    DigitalComponentRead,
    DigitalComponentUpdate,
    ComponentReorderRequest,
    EventHistoryRead,
    RecordCreate,
    RecordDraftComponentRead,
    RecordDraftCreate,
    RecordDraftRead,
    RecordDraftUpdate,
    RecordRead,
    RecordUpdate,
    SearchRequest,
    SearchResponse,
)
from .search import search_rows
from .user_management import router as user_management_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="ERMS API",
    version="0.1.0",
    description="REST API for the Electronic Records Management System.",
    lifespan=lifespan,
)
app.include_router(user_management_router)


def _request_uuid(value: str | None, header_name: str) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(value))
    except ValueError as exception:
        raise ValueError(f"{header_name} must be a valid UUID") from exception


@app.middleware("http")
async def audit_request_context(request: Request, call_next):
    try:
        request_id = _request_uuid(request.headers.get("X-Request-ID"), "X-Request-ID")
        correlation_header = request.headers.get("X-Correlation-ID")
        correlation_id = (
            _request_uuid(correlation_header, "X-Correlation-ID")
            if correlation_header
            else request_id
        )
    except ValueError as exception:
        return JSONResponse(status_code=400, content={"detail": str(exception)})

    change_reason = request.headers.get("X-Change-Reason", "")
    if len(change_reason) > 2000:
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Change-Reason cannot exceed 2000 characters"},
        )

    request_token = request_id_context.set(request_id)
    correlation_token = correlation_id_context.set(correlation_id)
    actor_token = actor_type_context.set("anonymous")
    source_token = event_source_context.set("api")
    reason_token = change_reason_context.set(change_reason)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        change_reason_context.reset(reason_token)
        event_source_context.reset(source_token)
        actor_type_context.reset(actor_token)
        correlation_id_context.reset(correlation_token)
        request_id_context.reset(request_token)


@app.exception_handler(psycopg.Error)
async def database_error_handler(_, exception: psycopg.Error):
    sqlstate = exception.sqlstate
    if sqlstate in {"23503", "23505", "P0001"}:
        status_code = status.HTTP_409_CONFLICT
        detail = exception.diag.message_primary or "database constraint violated"
    elif isinstance(exception, (psycopg.IntegrityError, psycopg.DataError)):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = exception.diag.message_primary or "database constraint violated"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "database operation failed"
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


@app.get("/health", tags=["system"])
def health(connection: Connection = Depends(get_connection)) -> dict[str, str]:
    connection.execute("SELECT 1")
    return {"status": "ok"}


@app.post(
    "/api/v1/aggregations",
    response_model=AggregationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["aggregations"],
)
def create_aggregation(
    payload: AggregationCreate,
    connection: Connection = Depends(get_connection),
):
    return create_row(connection, "aggregations", payload.model_dump())


@app.get("/api/v1/aggregations", response_model=list[AggregationRead], tags=["aggregations"])
def list_aggregations(
    parent_aggregation_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "aggregations",
        limit=limit,
        offset=offset,
        filters={"parent_aggregation_id": parent_aggregation_id},
    )


@app.post(
    "/api/v1/aggregations/search",
    response_model=SearchResponse[AggregationRead],
    tags=["aggregations"],
)
def search_aggregations(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection),
):
    return search_rows(connection, "aggregations", payload)


@app.get("/api/v1/aggregations/{aggregation_id}", response_model=AggregationRead, tags=["aggregations"])
def get_aggregation(aggregation_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "aggregations", aggregation_id)


@app.patch("/api/v1/aggregations/{aggregation_id}", response_model=AggregationRead, tags=["aggregations"])
def update_aggregation(
    aggregation_id: int,
    payload: AggregationUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection, "aggregations", aggregation_id, payload.model_dump(exclude_unset=True), version
    )


@app.delete("/api/v1/aggregations/{aggregation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["aggregations"])
def delete_aggregation(aggregation_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection)):
    delete_row(connection, "aggregations", aggregation_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/records", response_model=RecordRead, status_code=status.HTTP_201_CREATED, tags=["records"])
def create_record(payload: RecordCreate, connection: Connection = Depends(get_connection)):
    return create_row(connection, "records", payload.model_dump())


@app.get("/api/v1/records", response_model=list[RecordRead], tags=["records"])
def list_records(
    aggregation_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "records",
        limit=limit,
        offset=offset,
        filters={"aggregation_id": aggregation_id},
    )


@app.post(
    "/api/v1/records/search",
    response_model=SearchResponse[RecordRead],
    tags=["records"],
)
def search_records(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection),
):
    return search_rows(connection, "records", payload)


@app.get("/api/v1/records/{record_id}", response_model=RecordRead, tags=["records"])
def get_record(record_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "records", record_id)


@app.patch("/api/v1/records/{record_id}", response_model=RecordRead, tags=["records"])
def update_record(
    record_id: int,
    payload: RecordUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    return update_row(connection, "records", record_id, payload.model_dump(exclude_unset=True), version)


@app.delete("/api/v1/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["records"])
def delete_record(record_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection)):
    delete_row(connection, "records", record_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _open_draft(connection: Connection, draft_id: int, *, lock: bool = False) -> dict:
    suffix = " FOR UPDATE" if lock else ""
    draft = connection.execute(
        f"SELECT * FROM record_drafts WHERE id = %s{suffix}", (draft_id,)
    ).fetchone()
    if draft is None:
        raise HTTPException(status_code=404, detail="record draft not found")
    if draft["status"] != "open":
        raise HTTPException(status_code=409, detail="record draft is no longer open")
    if draft["expires_at"] <= datetime.now(draft["expires_at"].tzinfo):
        raise HTTPException(status_code=410, detail="record draft has expired")
    return draft


@app.post("/api/v1/record-drafts", response_model=RecordDraftRead, status_code=201, tags=["record drafts"])
def create_record_draft(payload: RecordDraftCreate, connection: Connection = Depends(get_connection)):
    values = payload.model_dump(exclude_none=True)
    if not values:
        return connection.execute("INSERT INTO record_drafts DEFAULT VALUES RETURNING *").fetchone()
    return create_row(connection, "record_drafts", values)


@app.get("/api/v1/record-drafts/{draft_id}", response_model=RecordDraftRead, tags=["record drafts"])
def get_record_draft(draft_id: int, connection: Connection = Depends(get_connection)):
    return _open_draft(connection, draft_id)


@app.patch("/api/v1/record-drafts/{draft_id}", response_model=RecordDraftRead, tags=["record drafts"])
def update_record_draft(draft_id: int, payload: RecordDraftUpdate, connection: Connection = Depends(get_connection)):
    _open_draft(connection, draft_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _open_draft(connection, draft_id)
    assignments = ", ".join(f"{key} = %s" for key in values)
    return connection.execute(
        f"UPDATE record_drafts SET {assignments} WHERE id = %s RETURNING *",
        (*values.values(), draft_id),
    ).fetchone()


@app.delete("/api/v1/record-drafts/{draft_id}", status_code=204, tags=["record drafts"])
def discard_record_draft(draft_id: int, connection: Connection = Depends(get_connection)):
    _open_draft(connection, draft_id, lock=True)
    connection.execute("DELETE FROM record_drafts WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.get("/api/v1/record-drafts/{draft_id}/components", response_model=list[RecordDraftComponentRead], tags=["record drafts"])
def list_record_draft_components(draft_id: int, connection: Connection = Depends(get_connection)):
    _open_draft(connection, draft_id)
    return list(connection.execute(
        """SELECT id, draft_id, component_order, file_name, date_created,
                  date_originated, mime_type, size_in_bytes, checksum_algo,
                  checksum_value, 'staged' AS content_status,
                  'temporary' AS storage_backend
           FROM record_draft_components WHERE draft_id = %s ORDER BY component_order""",
        (draft_id,),
    ).fetchall())


@app.post("/api/v1/record-drafts/{draft_id}/components", response_model=RecordDraftComponentRead, status_code=201, tags=["record drafts"])
def upload_record_draft_component(
    draft_id: int,
    file: UploadFile = File(...),
    component_order: int = Form(..., gt=0),
    date_originated: datetime | None = Form(default=None),
    connection: Connection = Depends(get_connection),
):
    _open_draft(connection, draft_id, lock=True)
    uploaded = read_upload(file)
    component = connection.execute(
        """INSERT INTO record_draft_components
               (draft_id, component_order, file_name, date_originated, mime_type,
                size_in_bytes, checksum_algo, checksum_value, content)
           VALUES (%s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), %s, %s, 'sha256', %s, %s)
           RETURNING id, draft_id, component_order, file_name, date_created,
                     date_originated, mime_type, size_in_bytes, checksum_algo,
                     checksum_value, 'staged' AS content_status,
                     'temporary' AS storage_backend""",
        (draft_id, component_order, file.filename or "unnamed", date_originated,
         file.content_type or "application/octet-stream", uploaded.size_in_bytes,
         uploaded.checksum_value, uploaded.content),
    ).fetchone()
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return component


def _reorder_components(connection: Connection, table: str, parent_column: str, parent_id: int, payload: ComponentReorderRequest) -> None:
    requested = {item.id: item.component_order for item in payload.components}
    if len(requested) != len(payload.components) or set(requested.values()) != set(range(1, len(requested) + 1)):
        raise HTTPException(status_code=422, detail="component order must contain each position from 1 through the component count")
    existing = {
        row["id"] for row in connection.execute(
            f"SELECT id FROM {table} WHERE {parent_column} = %s FOR UPDATE", (parent_id,)
        ).fetchall()
    }
    if existing != set(requested):
        raise HTTPException(status_code=422, detail="component list must contain every component exactly once")
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for component_id, position in requested.items():
        connection.execute(
            f"UPDATE {table} SET component_order = %s WHERE id = %s", (position, component_id)
        )


@app.put("/api/v1/record-drafts/{draft_id}/components/order", status_code=204, tags=["record drafts"])
def reorder_record_draft_components(draft_id: int, payload: ComponentReorderRequest, connection: Connection = Depends(get_connection)):
    _open_draft(connection, draft_id, lock=True)
    _reorder_components(connection, "record_draft_components", "draft_id", draft_id, payload)
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.delete("/api/v1/record-drafts/{draft_id}/components/{component_id}", status_code=204, tags=["record drafts"])
def delete_record_draft_component(draft_id: int, component_id: int, connection: Connection = Depends(get_connection)):
    _open_draft(connection, draft_id, lock=True)
    deleted = connection.execute(
        "DELETE FROM record_draft_components WHERE id = %s AND draft_id = %s RETURNING id",
        (component_id, draft_id),
    ).fetchone()
    if deleted is None:
        raise HTTPException(status_code=404, detail="record draft component not found")
    rows = connection.execute(
        "SELECT id FROM record_draft_components WHERE draft_id = %s ORDER BY component_order", (draft_id,)
    ).fetchall()
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for position, row in enumerate(rows, 1):
        connection.execute("UPDATE record_draft_components SET component_order = %s WHERE id = %s", (position, row["id"]))
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.post("/api/v1/record-drafts/{draft_id}/commit", response_model=RecordRead, status_code=201, tags=["record drafts"])
def commit_record_draft(draft_id: int, connection: Connection = Depends(get_connection)):
    draft = _open_draft(connection, draft_id, lock=True)
    missing = [name for name in ("aggregation_id", "record_number", "title") if not draft.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"draft is missing required fields: {', '.join(missing)}")
    record = create_row(connection, "records", {
        "aggregation_id": draft["aggregation_id"], "record_number": draft["record_number"],
        "title": draft["title"], "description": draft["description"],
        "date_originated": draft["date_originated"],
    })
    components = connection.execute(
        "SELECT * FROM record_draft_components WHERE draft_id = %s ORDER BY component_order FOR UPDATE", (draft_id,)
    ).fetchall()
    for staged in components:
        component = create_row(connection, "digital_components", {
            "record_id": record["id"], "component_order": staged["component_order"],
            "file_name": staged["file_name"], "date_originated": staged["date_originated"],
            "mime_type": staged["mime_type"], "size_in_bytes": staged["size_in_bytes"],
            "checksum_algo": staged["checksum_algo"], "checksum_value": staged["checksum_value"],
            "storage_backend": "postgresql", "content_status": "available",
        })
        configured_storage().store(connection, component["id"], bytes(staged["content"]))
        _append_content_event(connection, component["id"], "CONTENT_UPLOADED", {
            "file_name": component["file_name"], "mime_type": component["mime_type"],
            "size_in_bytes": component["size_in_bytes"], "checksum_algo": component["checksum_algo"],
            "checksum_value": component["checksum_value"], "record_creation": True,
        })
    connection.execute("DELETE FROM record_drafts WHERE id = %s", (draft_id,))
    return record


@app.post(
    "/api/v1/digital-components",
    response_model=DigitalComponentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["digital components"],
)
def create_digital_component(
    payload: DigitalComponentCreate,
    connection: Connection = Depends(get_connection),
):
    return create_row(connection, "digital_components", payload.model_dump())


@app.get(
    "/api/v1/digital-components",
    response_model=list[DigitalComponentRead],
    tags=["digital components"],
)
def list_digital_components(
    record_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "digital_components",
        limit=limit,
        offset=offset,
        filters={"record_id": record_id},
        order_by=("record_id", "component_order"),
    )


@app.post(
    "/api/v1/digital-components/search",
    response_model=SearchResponse[DigitalComponentRead],
    tags=["digital components"],
)
def search_digital_components(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection),
):
    return search_rows(connection, "digital_components", payload)


@app.get(
    "/api/v1/digital-components/{component_id}",
    response_model=DigitalComponentRead,
    tags=["digital components"],
)
def get_digital_component(component_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "digital_components", component_id)


@app.patch(
    "/api/v1/digital-components/{component_id}",
    response_model=DigitalComponentRead,
    tags=["digital components"],
)
def update_digital_component(
    component_id: int,
    payload: DigitalComponentUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection,
        "digital_components",
        component_id,
        payload.model_dump(exclude_unset=True),
        version,
    )


@app.delete(
    "/api/v1/digital-components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["digital components"],
)
def delete_digital_component(
    component_id: int,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    component = get_or_404(connection, "digital_components", component_id)
    delete_row(connection, "digital_components", component_id, version)
    remaining = connection.execute(
        "SELECT id FROM digital_components WHERE record_id = %s ORDER BY component_order",
        (component["record_id"],),
    ).fetchall()
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for position, row in enumerate(remaining, 1):
        connection.execute(
            "UPDATE digital_components SET component_order = %s WHERE id = %s",
            (position, row["id"]),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put(
    "/api/v1/records/{record_id}/digital-components/order",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["digital components"],
)
def reorder_digital_components(
    record_id: int,
    payload: ComponentReorderRequest,
    connection: Connection = Depends(get_connection),
):
    get_or_404(connection, "records", record_id)
    _reorder_components(connection, "digital_components", "record_id", record_id, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _append_content_event(
    connection: Connection,
    component_id: int,
    operation: str,
    metadata: dict,
) -> None:
    connection.execute(
        "SELECT append_domain_event(%s, %s, %s, %s)",
        ("digital_component", component_id, operation, Jsonb(metadata)),
    )


@app.post(
    "/api/v1/records/{record_id}/digital-components/upload",
    response_model=DigitalComponentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["digital component content"],
)
def upload_digital_component(
    record_id: int,
    file: UploadFile = File(...),
    component_order: int = Form(..., gt=0),
    date_originated: datetime | None = Form(default=None),
    connection: Connection = Depends(get_connection),
):
    get_or_404(connection, "records", record_id)
    uploaded = read_upload(file)
    mime_type = file.content_type or "application/octet-stream"
    component = create_row(
        connection,
        "digital_components",
        {
            "record_id": record_id,
            "component_order": component_order,
            "file_name": file.filename or "unnamed",
            "date_originated": date_originated,
            "mime_type": mime_type,
            "size_in_bytes": uploaded.size_in_bytes,
            "checksum_algo": "sha256",
            "checksum_value": uploaded.checksum_value,
            "storage_backend": "postgresql",
            "content_status": "available",
        },
    )
    configured_storage().store(connection, component["id"], uploaded.content)
    _append_content_event(
        connection,
        component["id"],
        "CONTENT_UPLOADED",
        {"file_name": component["file_name"], "mime_type": mime_type,
         "size_in_bytes": uploaded.size_in_bytes, "checksum_algo": "sha256",
         "checksum_value": uploaded.checksum_value},
    )
    return component


@app.get(
    "/api/v1/digital-components/{component_id}/content",
    tags=["digital component content"],
)
def download_digital_component_content(
    component_id: int,
    connection: Connection = Depends(get_connection),
):
    component = get_or_404(connection, "digital_components", component_id)
    content = configured_storage().read(connection, component_id)
    if content is None or component["content_status"] != "available":
        raise HTTPException(status_code=404, detail="digital component content not found")
    _append_content_event(connection, component_id, "CONTENT_DOWNLOADED", {
        "size_in_bytes": component["size_in_bytes"],
        "checksum_algo": component["checksum_algo"],
        "checksum_value": component["checksum_value"],
    })
    encoded_name = quote(component["file_name"], safe="")
    return StreamingResponse(
        BytesIO(content),
        media_type=component["mime_type"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@app.put(
    "/api/v1/digital-components/{component_id}/content",
    response_model=DigitalComponentRead,
    tags=["digital component content"],
)
def replace_digital_component_content(
    component_id: int,
    file: UploadFile = File(...),
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    uploaded = read_upload(file)
    mime_type = file.content_type or "application/octet-stream"
    component = update_row(connection, "digital_components", component_id, {
        "file_name": file.filename or "unnamed",
        "mime_type": mime_type,
        "size_in_bytes": uploaded.size_in_bytes,
        "checksum_algo": "sha256",
        "checksum_value": uploaded.checksum_value,
        "storage_backend": "postgresql",
        "storage_key": None,
        "content_status": "available",
    }, version)
    configured_storage().store(connection, component_id, uploaded.content)
    _append_content_event(connection, component_id, "CONTENT_REPLACED", {
        "file_name": component["file_name"], "mime_type": mime_type,
        "size_in_bytes": uploaded.size_in_bytes, "checksum_algo": "sha256",
        "checksum_value": uploaded.checksum_value,
    })
    return component


@app.delete(
    "/api/v1/digital-components/{component_id}/content",
    response_model=DigitalComponentRead,
    tags=["digital component content"],
)
def delete_digital_component_content(
    component_id: int,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection),
):
    configured_storage().delete(connection, component_id)
    component = update_row(connection, "digital_components", component_id, {
        "content_status": "deleted",
    }, version)
    _append_content_event(connection, component_id, "CONTENT_DELETED", {
        "size_in_bytes": component["size_in_bytes"],
        "checksum_algo": component["checksum_algo"],
        "checksum_value": component["checksum_value"],
    })
    return component


@app.get(
    "/api/v1/event-history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def list_event_history(
    entity_type: str | None = None,
    entity_id: int | None = None,
    operation: str | None = None,
    request_id: UUID | None = None,
    correlation_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "event_history",
        limit=limit,
        offset=offset,
        filters={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operation": operation,
            "request_id": request_id,
            "correlation_id": correlation_id,
        },
        order_by=("occurred_at", "id"),
        descending=True,
    )


@app.post(
    "/api/v1/event-history/search",
    response_model=SearchResponse[EventHistoryRead],
    tags=["event history"],
)
def search_event_history(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection),
):
    return search_rows(connection, "event_history", payload)


@app.get(
    "/api/v1/event-history/{event_id}",
    response_model=EventHistoryRead,
    tags=["event history"],
)
def get_event_history(event_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "event_history", event_id)


def _entity_history(
    connection: Connection,
    entity_type: str,
    entity_id: int,
    limit: int,
    offset: int,
):
    return list_rows(
        connection,
        "event_history",
        limit=limit,
        offset=offset,
        filters={"entity_type": entity_type, "entity_id": entity_id},
        order_by=("occurred_at", "id"),
        descending=True,
    )


@app.get(
    "/api/v1/aggregations/{aggregation_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_aggregation_history(
    aggregation_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return _entity_history(connection, "aggregation", aggregation_id, limit, offset)


@app.get(
    "/api/v1/records/{record_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_record_history(
    record_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return _entity_history(connection, "record", record_id, limit, offset)


@app.get(
    "/api/v1/digital-components/{component_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_digital_component_history(
    component_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return _entity_history(connection, "digital_component", component_id, limit, offset)
