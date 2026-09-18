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


ORG_UNIT_NODE_SQL = """
    WITH RECURSIVE ancestors AS (
        SELECT source.id AS source_id, source.id, source.parent_org_unit_id,
               source.status, source.code, source.name
          FROM org_units source
        UNION ALL
        SELECT ancestors.source_id, parent.id, parent.parent_org_unit_id,
               parent.status, parent.code, parent.name
          FROM ancestors
          JOIN org_units parent ON parent.id = ancestors.parent_org_unit_id
    )
    SELECT unit.id, unit.parent_org_unit_id, unit.code, unit.name,
           unit.description, unit.status, unit.date_created,
           unit.date_deactivated, unit.version,
           CASE WHEN EXISTS (
               SELECT 1 FROM ancestors
                WHERE source_id=unit.id AND status='inactive'
           ) THEN 'inactive' ELSE 'active' END AS effective_status,
           (SELECT jsonb_build_object('id', inactive.id, 'code', inactive.code,
                                      'name', inactive.name)
              FROM ancestors inactive
             WHERE inactive.source_id=unit.id AND inactive.status='inactive'
             ORDER BY CASE WHEN inactive.id=unit.id THEN 0 ELSE 1 END, inactive.id
             LIMIT 1) AS inactive_source,
           (SELECT count(*) FROM org_units child
             WHERE child.parent_org_unit_id=unit.id) AS child_org_unit_count,
           (SELECT count(*) FROM roles role WHERE role.org_unit_id=unit.id) AS role_count
      FROM org_units unit
"""


ROLE_NODE_SQL = """
    WITH RECURSIVE ancestors AS (
        SELECT source.id AS source_id, source.id, source.parent_org_unit_id,
               source.status, source.code, source.name
          FROM org_units source
        UNION ALL
        SELECT ancestors.source_id, parent.id, parent.parent_org_unit_id,
               parent.status, parent.code, parent.name
          FROM ancestors
          JOIN org_units parent ON parent.id = ancestors.parent_org_unit_id
    )
    SELECT role.id, role.org_unit_id, role.supervisor_role_id, role.code,
           role.name, role.description, role.status, role.date_created,
           role.date_deactivated, role.version,
           unit.code AS org_unit_code, unit.name AS org_unit_name,
           supervisor.code AS supervisor_role_code,
           supervisor.name AS supervisor_role_name,
           CASE WHEN role.status='active' AND NOT EXISTS (
               SELECT 1 FROM ancestors
                WHERE source_id=role.org_unit_id AND status='inactive'
           ) THEN 'active' ELSE 'inactive' END AS effective_status,
           (SELECT count(*) FROM roles child
             WHERE child.supervisor_role_id=role.id) AS subordinate_role_count,
           (SELECT count(*) FROM user_role_assignments assignment
             WHERE assignment.role_id=role.id) AS assigned_user_count,
           (SELECT count(*) FROM user_role_assignments assignment
             WHERE assignment.role_id=role.id
               AND assignment.valid_from <= CURRENT_TIMESTAMP
               AND (assignment.valid_until IS NULL OR assignment.valid_until > CURRENT_TIMESTAMP)
           ) AS current_assignment_count
      FROM roles role
      JOIN org_units unit ON unit.id=role.org_unit_id
 LEFT JOIN roles supervisor ON supervisor.id=role.supervisor_role_id
"""


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


@router.get("/organization/roots", tags=["organization browser"])
def browse_organization_roots(
    limit: int = Query(100, ge=1, le=100),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list(connection.execute(
        f"SELECT * FROM ({ORG_UNIT_NODE_SQL}) source "
        "WHERE parent_org_unit_id IS NULL ORDER BY code COLLATE \"C\", id LIMIT %s",
        (limit,),
    ).fetchall())


@router.get("/organization/org-units/{org_unit_id}/children", tags=["organization browser"])
def browse_organization_children(
    org_unit_id: int, include_roles: bool = True,
    limit: int = Query(100, ge=1, le=100),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if connection.execute("SELECT 1 FROM org_units WHERE id=%s", (org_unit_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="organization unit not found")
    units = list(connection.execute(
        f"SELECT * FROM ({ORG_UNIT_NODE_SQL}) source "
        "WHERE parent_org_unit_id=%s ORDER BY code COLLATE \"C\", id LIMIT %s",
        (org_unit_id, limit),
    ).fetchall())
    roles = []
    if include_roles:
        roles = list(connection.execute(
            f"SELECT * FROM ({ROLE_NODE_SQL}) source "
            "WHERE org_unit_id=%s ORDER BY code COLLATE \"C\", id LIMIT %s",
            (org_unit_id, limit),
        ).fetchall())
    return {"org_units": units, "roles": roles}


@router.get("/organization/roles/{role_id}/users", tags=["organization browser"])
def browse_role_users(
    role_id: int, validity: Literal["all", "current", "future", "expired"] = "all",
    limit: int = Query(100, ge=1, le=100),
    connection: Connection = Depends(get_connection, scope="function"),
):
    role = connection.execute("SELECT id FROM roles WHERE id=%s", (role_id,)).fetchone()
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    validity_sql = {
        "all": "TRUE",
        "current": "assignment.valid_from <= CURRENT_TIMESTAMP AND (assignment.valid_until IS NULL OR assignment.valid_until > CURRENT_TIMESTAMP)",
        "future": "assignment.valid_from > CURRENT_TIMESTAMP",
        "expired": "assignment.valid_until IS NOT NULL AND assignment.valid_until <= CURRENT_TIMESTAMP",
    }[validity]
    return list(connection.execute(
        f"""SELECT assignment.id AS assignment_id, assignment.role_id,
                   assignment.valid_from, assignment.valid_until,
                   assignment.version AS assignment_version,
                   CASE WHEN assignment.valid_from > CURRENT_TIMESTAMP THEN 'future'
                        WHEN assignment.valid_until IS NOT NULL AND assignment.valid_until <= CURRENT_TIMESTAMP THEN 'expired'
                        ELSE 'current' END AS assignment_validity,
                   role.code AS role_code, role.name AS role_name,
                   person.id, person.name, person.email, person.external_id,
                   person.account_type, person.status, person.date_created,
                   person.date_deactivated, person.version
              FROM user_role_assignments assignment
              JOIN users person ON person.id=assignment.user_id
              JOIN roles role ON role.id=assignment.role_id
             WHERE assignment.role_id=%s AND {validity_sql}
             ORDER BY person.name COLLATE "C", person.id, assignment.id
             LIMIT %s""",
        (role_id, limit),
    ).fetchall())


@router.get("/organization/org-units/{org_unit_id}/summary", tags=["organization browser"])
def browse_org_unit_summary(
    org_unit_id: int, connection: Connection = Depends(get_connection, scope="function"),
):
    row = connection.execute(
        f"SELECT * FROM ({ORG_UNIT_NODE_SQL}) source WHERE id=%s", (org_unit_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="organization unit not found")
    if row["parent_org_unit_id"]:
        row["parent"] = connection.execute(
            "SELECT id, code, name FROM org_units WHERE id=%s", (row["parent_org_unit_id"],),
        ).fetchone()
    else:
        row["parent"] = None
    return row


@router.get("/organization/roles/{role_id}/summary", tags=["organization browser"])
def browse_role_summary(
    role_id: int, connection: Connection = Depends(get_connection, scope="function"),
):
    row = connection.execute(
        f"SELECT * FROM ({ROLE_NODE_SQL}) source WHERE id=%s", (role_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="role not found")
    counts = connection.execute(
        """SELECT count(*) FILTER (WHERE valid_from > CURRENT_TIMESTAMP) AS future_assignment_count,
                  count(*) FILTER (WHERE valid_until IS NOT NULL AND valid_until <= CURRENT_TIMESTAMP) AS expired_assignment_count
             FROM user_role_assignments WHERE role_id=%s""", (role_id,),
    ).fetchone()
    return {**row, **counts}


@router.get("/organization/search", tags=["organization browser"])
def search_organization_structure(
    query: str = Query(min_length=1, max_length=200),
    entity_type: Literal["all", "org_unit", "role", "user"] = "all",
    status: Literal["all", "active", "inactive", "suspended"] = "all",
    limit: int = Query(50, ge=1, le=100),
    connection: Connection = Depends(get_connection, scope="function"),
):
    pattern = f"%{query.strip()}%"
    status_filter = "TRUE" if status == "all" else "source.effective_status=%s"
    status_parameters: tuple[Any, ...] = () if status == "all" else (status,)
    results: list[dict[str, Any]] = []
    if entity_type in {"all", "org_unit"}:
        results.extend({"type": "org_unit", **row} for row in connection.execute(
            f"""WITH RECURSIVE paths AS (
                    SELECT unit.id, unit.parent_org_unit_id,
                           ARRAY[unit.id]::bigint[] AS reverse_path
                      FROM org_units unit
                    UNION ALL
                    SELECT paths.id, parent.parent_org_unit_id,
                           paths.reverse_path || parent.id
                      FROM paths JOIN org_units parent
                        ON parent.id=paths.parent_org_unit_id
                )
                SELECT source.id, source.code, source.name, source.status,
                       source.effective_status,
                       (SELECT array_agg(path_id ORDER BY ordinal DESC)
                          FROM unnest(path.reverse_path) WITH ORDINALITY p(path_id, ordinal)
                       ) AS org_unit_path
                  FROM ({ORG_UNIT_NODE_SQL}) source
                  JOIN paths path ON path.id=source.id AND path.parent_org_unit_id IS NULL
                 WHERE (source.code ILIKE %s OR source.name ILIKE %s OR COALESCE(source.description,'') ILIKE %s)
                   AND {status_filter}
                 ORDER BY source.code LIMIT %s""",
            (pattern, pattern, pattern, *status_parameters, limit),
        ).fetchall())
    if entity_type in {"all", "role"}:
        results.extend({"type": "role", **row} for row in connection.execute(
            f"""WITH RECURSIVE paths AS (
                    SELECT unit.id, unit.parent_org_unit_id,
                           ARRAY[unit.id]::bigint[] AS reverse_path
                      FROM org_units unit
                    UNION ALL
                    SELECT paths.id, parent.parent_org_unit_id,
                           paths.reverse_path || parent.id
                      FROM paths JOIN org_units parent
                        ON parent.id=paths.parent_org_unit_id
                )
                SELECT source.id, source.code, source.name, source.status,
                       source.effective_status, source.org_unit_id,
                       (SELECT array_agg(path_id ORDER BY ordinal DESC)
                          FROM unnest(path.reverse_path) WITH ORDINALITY p(path_id, ordinal)
                       ) AS org_unit_path
                  FROM ({ROLE_NODE_SQL}) source
                  JOIN paths path ON path.id=source.org_unit_id AND path.parent_org_unit_id IS NULL
                 WHERE (source.code ILIKE %s OR source.name ILIKE %s OR COALESCE(source.description,'') ILIKE %s)
                   AND {status_filter}
                 ORDER BY source.code LIMIT %s""",
            (pattern, pattern, pattern, *status_parameters, limit),
        ).fetchall())
    if entity_type in {"all", "user"}:
        results.extend({"type": "user", **row} for row in connection.execute(
            f"""WITH RECURSIVE paths AS (
                    SELECT unit.id, unit.parent_org_unit_id,
                           ARRAY[unit.id]::bigint[] AS reverse_path
                      FROM org_units unit
                    UNION ALL
                    SELECT paths.id, parent.parent_org_unit_id,
                           paths.reverse_path || parent.id
                      FROM paths JOIN org_units parent
                        ON parent.id=paths.parent_org_unit_id
                )
                SELECT DISTINCT person.id, person.name, person.email, person.status,
                              assignment.role_id, assignment.id AS assignment_id,
                              role.code AS role_code, role.name AS role_name,
                              (SELECT array_agg(path_id ORDER BY ordinal DESC)
                                 FROM unnest(path.reverse_path) WITH ORDINALITY p(path_id, ordinal)
                              ) AS org_unit_path
                   FROM users person
              LEFT JOIN user_role_assignments assignment ON assignment.user_id=person.id
              LEFT JOIN roles role ON role.id=assignment.role_id
              LEFT JOIN paths path ON path.id=role.org_unit_id AND path.parent_org_unit_id IS NULL
                  WHERE (person.name ILIKE %s OR COALESCE(person.email,'') ILIKE %s)
                    AND {status_filter.replace('source.effective_status', 'person.status')}
               ORDER BY person.name, person.id LIMIT %s""",
            (pattern, pattern, *status_parameters, limit),
        ).fetchall())
    return results[:limit]
