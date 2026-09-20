from typing import Any

from fastapi import HTTPException
from psycopg import Connection, sql


READ_VISIBILITY = {
    "aggregations": sql.SQL("current_user_can_view_aggregation(id)"),
    "records": sql.SQL("current_user_can_view_record(id)"),
    "digital_components": sql.SQL(
        "EXISTS (SELECT 1 FROM records visible_record "
        "WHERE visible_record.id=record_id AND current_user_can_list_record_components(visible_record.id))"
    ),
}


def redact_hidden_relationships(
    connection: Connection, table: str, rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove protected parent identifiers with one bounded set query."""
    relation = {"aggregations": "parent_aggregation_id", "records": "aggregation_id"}.get(table)
    if relation is None:
        return rows
    parent_ids = sorted({row[relation] for row in rows if row.get(relation) is not None})
    if not parent_ids:
        return rows
    visible = {
        row["id"] for row in connection.execute(
            "SELECT id FROM aggregations WHERE id=ANY(%s) AND current_user_can_view_aggregation(id)",
            (parent_ids,),
        ).fetchall()
    }
    for row in rows:
        if row.get(relation) is not None and row[relation] not in visible:
            row[relation] = None
    return rows


def get_or_404(connection: Connection, table: str, entity_id: int) -> dict[str, Any]:
    source = "authorized_event_history" if table == "event_history" else table
    query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(source))
    if table in READ_VISIBILITY:
        query += sql.SQL(" AND ") + READ_VISIBILITY[table]
    row = connection.execute(query, (entity_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{table.rstrip('s')} not found")
    return redact_hidden_relationships(connection, table, [row])[0]


def list_rows(
    connection: Connection,
    table: str,
    *,
    limit: int,
    offset: int,
    filters: dict[str, Any] | None = None,
    order_by: tuple[str, ...] = ("id",),
    descending: bool = False,
) -> list[dict[str, Any]]:
    filters = {key: value for key, value in (filters or {}).items() if value is not None}
    source = "authorized_event_history" if table == "event_history" else table
    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(source))
    parameters: list[Any] = []

    clauses = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in filters
    ]
    parameters.extend(filters.values())
    if table in READ_VISIBILITY:
        clauses.append(READ_VISIBILITY[table])
    if clauses:
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)

    direction = sql.SQL(" DESC") if descending else sql.SQL(" ASC")
    query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
        sql.Identifier(column) + direction for column in order_by
    )
    query += sql.SQL(" LIMIT %s OFFSET %s")
    parameters.extend((limit, offset))
    rows = list(connection.execute(query, parameters).fetchall())
    return redact_hidden_relationships(connection, table, rows)


def create_row(connection: Connection, table: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = list(values)
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    return connection.execute(query, [values[column] for column in columns]).fetchone()


def update_row(
    connection: Connection,
    table: str,
    entity_id: int,
    values: dict[str, Any],
    expected_version: int,
) -> dict[str, Any]:
    if not values:
        row = get_or_404(connection, table, entity_id)
        if row["version"] != expected_version:
            raise HTTPException(status_code=412, detail="entity has changed")
        return row

    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in values
    ]
    query = sql.SQL(
        "UPDATE {} SET {} WHERE id = %s AND version = %s RETURNING *"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(assignments),
    )
    row = connection.execute(
        query, [*values.values(), entity_id, expected_version]
    ).fetchone()
    if row is None:
        current = get_or_404(connection, table, entity_id)
        raise HTTPException(
            status_code=412,
            detail={
                "message": "entity has changed",
                "current_version": current["version"],
            },
        )
    return row


def delete_row(
    connection: Connection,
    table: str,
    entity_id: int,
    expected_version: int,
) -> None:
    query = sql.SQL(
        "DELETE FROM {} WHERE id = %s AND version = %s RETURNING id"
    ).format(
        sql.Identifier(table)
    )
    if connection.execute(query, (entity_id, expected_version)).fetchone() is None:
        current = get_or_404(connection, table, entity_id)
        raise HTTPException(
            status_code=412,
            detail={
                "message": "entity has changed",
                "current_version": current["version"],
            },
        )
