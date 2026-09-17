from __future__ import annotations

import base64
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from .database import get_connection
from .schemas import (
    AggregationRead,
    BrowseAggregationNode,
    BrowseClassificationNode,
    BrowsePage,
    BrowseRecordNode,
    ClassificationSchemeRead,
)


router = APIRouter(prefix="/api/v1/browse", tags=["classification browser"])


def _encode_cursor(scope: str, key: str, entity_id: int, query: str) -> str:
    payload = json.dumps(
        {"scope": scope, "key": key, "id": entity_id, "query": query},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, scope: str, query: str) -> tuple[str, int] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("scope") != scope or payload.get("query") != query:
            raise ValueError
        return str(payload["key"]), int(payload["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid or mismatched browse cursor")


def _page(
    connection: Connection,
    *,
    scope: str,
    source_sql: str,
    parameters: list[Any],
    key_column: str,
    query: str,
    query_columns: tuple[str, ...],
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    normalized_query = query.strip()
    filters: list[str] = []
    filter_parameters: list[Any] = []
    if normalized_query:
        filters.append("(" + " OR ".join(
            f"COALESCE({column}, '') ILIKE %s" for column in query_columns
        ) + ")")
        filter_parameters.extend([f"%{normalized_query}%"] * len(query_columns))

    decoded = _decode_cursor(cursor, scope, normalized_query)
    page_filters = list(filters)
    page_parameters = [*parameters, *filter_parameters]
    if decoded:
        page_filters.append(f"({key_column} COLLATE \"C\", id) > (%s COLLATE \"C\", %s)")
        page_parameters.extend(decoded)

    where_suffix = (" WHERE " + " AND ".join(filters)) if filters else ""
    page_where_suffix = (" WHERE " + " AND ".join(page_filters)) if page_filters else ""
    total = connection.execute(
        f"SELECT count(*) AS total FROM ({source_sql}) browse_source{where_suffix}",
        [*parameters, *filter_parameters],
    ).fetchone()["total"]
    rows = list(connection.execute(
        f"SELECT * FROM ({source_sql}) browse_source{page_where_suffix} "
        f"ORDER BY {key_column} COLLATE \"C\", id LIMIT %s",
        [*page_parameters, limit + 1],
    ).fetchall())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(
            scope, str(last[key_column]), int(last["id"]), normalized_query,
        )
    return {"items": items, "next_cursor": next_cursor, "total": int(total)}


CLASSIFICATION_SOURCE = """
    SELECT c.id, c.classification_scheme_id, c.parent_classification_id,
           c.code, c.title, c.description, c.is_terminal, c.date_deactivated,
           (SELECT count(*) FROM classifications child
             WHERE child.parent_classification_id = c.id) AS child_classification_count,
           (SELECT count(*) FROM aggregations aggregation
             WHERE aggregation.classification_id = c.id
               AND aggregation.parent_aggregation_id IS NULL) AS root_aggregation_count
      FROM classifications c
"""

AGGREGATION_SOURCE = """
    SELECT a.id, a.parent_aggregation_id, a.classification_id,
           classification.code AS classification_code,
           classification.title AS classification_title,
           a.aggregation_number, a.title, a.description, a.date_created,
           a.date_opened, a.date_closed,
           (SELECT count(*) FROM aggregations child
             WHERE child.parent_aggregation_id = a.id) AS child_aggregation_count,
           (SELECT count(*) FROM records record
             WHERE record.aggregation_id = a.id) AS record_count
      FROM aggregations a
 LEFT JOIN classifications classification ON classification.id = a.classification_id
"""

RECORD_SOURCE = """
    SELECT r.id, r.aggregation_id, owner.aggregation_number,
           owner.title AS aggregation_title,
           r.record_number, r.title, r.description,
           r.date_created, r.date_originated,
           (SELECT count(*) FROM digital_components component
             WHERE component.record_id = r.id) AS digital_component_count
      FROM records r
      JOIN aggregations owner ON owner.id = r.aggregation_id
"""


@router.get("/classification-schemes", response_model=list[ClassificationSchemeRead])
def browse_schemes(connection: Connection = Depends(get_connection, scope="function")):
    return list(connection.execute(
        """SELECT * FROM classification_schemes
            WHERE date_published IS NOT NULL AND date_published <= CURRENT_TIMESTAMP
            ORDER BY title COLLATE \"C\", id"""
    ).fetchall())


@router.get(
    "/classification-schemes/{scheme_id}/roots",
    response_model=BrowsePage[BrowseClassificationNode],
)
def browse_classification_roots(
    scheme_id: int, limit: int = Query(50, ge=1, le=100), cursor: str | None = None,
    query: str = Query("", max_length=200),
    connection: Connection = Depends(get_connection, scope="function"),
):
    scheme = connection.execute(
        "SELECT id FROM classification_schemes WHERE id=%s AND date_published IS NOT NULL AND date_published <= CURRENT_TIMESTAMP",
        (scheme_id,),
    ).fetchone()
    if scheme is None:
        raise HTTPException(status_code=404, detail="published classification scheme not found")
    return _page(
        connection, scope=f"scheme:{scheme_id}:roots",
        source_sql=CLASSIFICATION_SOURCE + " WHERE c.classification_scheme_id=%s AND c.parent_classification_id IS NULL",
        parameters=[scheme_id], key_column="code", query=query,
        query_columns=("code", "title"), limit=limit, cursor=cursor,
    )


@router.get(
    "/classifications/{classification_id}/children",
    response_model=BrowsePage[BrowseClassificationNode],
)
def browse_classification_children(
    classification_id: int, limit: int = Query(50, ge=1, le=100), cursor: str | None = None,
    query: str = Query("", max_length=200),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if connection.execute("SELECT 1 FROM classifications WHERE id=%s", (classification_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="classification not found")
    return _page(
        connection, scope=f"classification:{classification_id}:children",
        source_sql=CLASSIFICATION_SOURCE + " WHERE c.parent_classification_id=%s",
        parameters=[classification_id], key_column="code", query=query,
        query_columns=("code", "title"), limit=limit, cursor=cursor,
    )


@router.get(
    "/classifications/{classification_id}/aggregations",
    response_model=BrowsePage[BrowseAggregationNode],
)
def browse_classification_aggregations(
    classification_id: int, limit: int = Query(50, ge=1, le=100), cursor: str | None = None,
    query: str = Query("", max_length=200),
    connection: Connection = Depends(get_connection, scope="function"),
):
    classification = connection.execute(
        "SELECT is_terminal FROM classifications WHERE id=%s", (classification_id,),
    ).fetchone()
    if classification is None:
        raise HTTPException(status_code=404, detail="classification not found")
    if not classification["is_terminal"]:
        raise HTTPException(status_code=409, detail="only terminal classifications govern aggregations")
    return _page(
        connection, scope=f"classification:{classification_id}:aggregations",
        source_sql=AGGREGATION_SOURCE + " WHERE a.classification_id=%s AND a.parent_aggregation_id IS NULL",
        parameters=[classification_id], key_column="aggregation_number", query=query,
        query_columns=("aggregation_number", "title"), limit=limit, cursor=cursor,
    )


@router.get(
    "/aggregations/{aggregation_id}/children",
    response_model=BrowsePage[BrowseAggregationNode],
)
def browse_aggregation_children(
    aggregation_id: int, limit: int = Query(50, ge=1, le=100), cursor: str | None = None,
    query: str = Query("", max_length=200),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if connection.execute("SELECT 1 FROM aggregations WHERE id=%s", (aggregation_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="aggregation not found")
    return _page(
        connection, scope=f"aggregation:{aggregation_id}:children",
        source_sql=AGGREGATION_SOURCE + " WHERE a.parent_aggregation_id=%s",
        parameters=[aggregation_id], key_column="aggregation_number", query=query,
        query_columns=("aggregation_number", "title"), limit=limit, cursor=cursor,
    )


@router.get(
    "/aggregations/{aggregation_id}/records",
    response_model=BrowsePage[BrowseRecordNode],
)
def browse_aggregation_records(
    aggregation_id: int, limit: int = Query(50, ge=1, le=100), cursor: str | None = None,
    query: str = Query("", max_length=200),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if connection.execute("SELECT 1 FROM aggregations WHERE id=%s", (aggregation_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="aggregation not found")
    return _page(
        connection, scope=f"aggregation:{aggregation_id}:records",
        source_sql=RECORD_SOURCE + " WHERE r.aggregation_id=%s",
        parameters=[aggregation_id], key_column="record_number", query=query,
        query_columns=("record_number", "title"), limit=limit, cursor=cursor,
    )


@router.get("/aggregations/{aggregation_id}/summary", response_model=BrowseAggregationNode)
def browse_aggregation_summary(
    aggregation_id: int, connection: Connection = Depends(get_connection, scope="function"),
):
    row = connection.execute(
        f"SELECT * FROM ({AGGREGATION_SOURCE}) browse_source WHERE id=%s", (aggregation_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="aggregation not found")
    return row


@router.get("/records/{record_id}/summary", response_model=BrowseRecordNode)
def browse_record_summary(
    record_id: int, connection: Connection = Depends(get_connection, scope="function"),
):
    row = connection.execute(
        f"SELECT * FROM ({RECORD_SOURCE}) browse_source WHERE id=%s", (record_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="record not found")
    return row
