from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, Query, Response, status
from fastapi.responses import JSONResponse
from psycopg import Connection

from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .database import close_pool, get_connection, open_pool
from .schemas import (
    AggregationCreate,
    AggregationRead,
    AggregationUpdate,
    DigitalComponentCreate,
    DigitalComponentRead,
    DigitalComponentUpdate,
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
