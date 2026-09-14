from typing import Any

from fastapi import HTTPException
from psycopg import Connection, sql


def get_or_404(connection: Connection, table: str, entity_id: int) -> dict[str, Any]:
    query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(table))
    row = connection.execute(query, (entity_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{table.rstrip('s')} not found")
    return row


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
    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
    parameters: list[Any] = []

    if filters:
        clauses = [
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in filters
        ]
        query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
        parameters.extend(filters.values())

    direction = sql.SQL(" DESC") if descending else sql.SQL(" ASC")
    query += sql.SQL(" ORDER BY ") + sql.SQL(", ").join(
        sql.Identifier(column) + direction for column in order_by
    )
    query += sql.SQL(" LIMIT %s OFFSET %s")
    parameters.extend((limit, offset))
    return list(connection.execute(query, parameters).fetchall())


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
) -> dict[str, Any]:
    if not values:
        return get_or_404(connection, table, entity_id)

    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in values
    ]
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(assignments),
    )
    row = connection.execute(query, [*values.values(), entity_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{table.rstrip('s')} not found")
    return row


def delete_row(connection: Connection, table: str, entity_id: int) -> None:
    query = sql.SQL("DELETE FROM {} WHERE id = %s RETURNING id").format(
        sql.Identifier(table)
    )
    if connection.execute(query, (entity_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail=f"{table.rstrip('s')} not found")
