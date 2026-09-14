from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, Query, Request, Response, status
from fastapi.responses import JSONResponse
from psycopg import Connection

from .audit_context import (
    actor_type_context,
    change_reason_context,
    correlation_id_context,
    event_source_context,
    request_id_context,
)
from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .database import close_pool, get_connection, open_pool
from .schemas import (
    AggregationCreate,
    AggregationRead,
    AggregationUpdate,
    DigitalComponentCreate,
    DigitalComponentRead,
    DigitalComponentUpdate,
    EventHistoryRead,
    RecordCreate,
    RecordRead,
    RecordUpdate,
    SearchRequest,
    SearchResponse,
)
from .search import search_rows


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
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection, "aggregations", aggregation_id, payload.model_dump(exclude_unset=True)
    )


@app.delete("/api/v1/aggregations/{aggregation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["aggregations"])
def delete_aggregation(aggregation_id: int, connection: Connection = Depends(get_connection)):
    delete_row(connection, "aggregations", aggregation_id)
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
    connection: Connection = Depends(get_connection),
):
    return update_row(connection, "records", record_id, payload.model_dump(exclude_unset=True))


@app.delete("/api/v1/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["records"])
def delete_record(record_id: int, connection: Connection = Depends(get_connection)):
    delete_row(connection, "records", record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection,
        "digital_components",
        component_id,
        payload.model_dump(exclude_unset=True),
    )


@app.delete(
    "/api/v1/digital-components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["digital components"],
)
def delete_digital_component(
    component_id: int,
    connection: Connection = Depends(get_connection),
):
    delete_row(connection, "digital_components", component_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
