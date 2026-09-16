from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from psycopg import Connection, sql
from pydantic import TypeAdapter, ValidationError

from .schemas import SearchExpression, SearchRequest


MAX_SEARCH_DEPTH = 5
MAX_SEARCH_CONDITIONS = 50
MAX_IN_VALUES = 100


class FieldType(str, Enum):
    INTEGER = "integer"
    TEXT = "text"
    DATETIME = "datetime"
    UUID = "uuid"


@dataclass(frozen=True)
class SearchField:
    type: FieldType
    nullable: bool = False


INTEGER = SearchField(FieldType.INTEGER)
NULLABLE_INTEGER = SearchField(FieldType.INTEGER, nullable=True)
TEXT = SearchField(FieldType.TEXT)
NULLABLE_TEXT = SearchField(FieldType.TEXT, nullable=True)
DATETIME = SearchField(FieldType.DATETIME)
NULLABLE_DATETIME = SearchField(FieldType.DATETIME, nullable=True)
NULLABLE_UUID = SearchField(FieldType.UUID, nullable=True)

SEARCH_FIELDS: dict[str, dict[str, SearchField]] = {
    "aggregations": {
        "id": INTEGER,
        "version": INTEGER,
        "parent_aggregation_id": NULLABLE_INTEGER,
        "aggregation_number": TEXT,
        "title": TEXT,
        "description": NULLABLE_TEXT,
        "date_created": DATETIME,
        "date_opened": DATETIME,
        "date_closed": NULLABLE_DATETIME,
    },
    "records": {
        "id": INTEGER,
        "version": INTEGER,
        "aggregation_id": INTEGER,
        "record_number": TEXT,
        "title": TEXT,
        "description": NULLABLE_TEXT,
        "date_created": DATETIME,
        "date_originated": DATETIME,
    },
    "digital_components": {
        "id": INTEGER,
        "version": INTEGER,
        "record_id": INTEGER,
        "component_order": INTEGER,
        "file_name": TEXT,
        "date_created": DATETIME,
        "date_originated": DATETIME,
        "mime_type": TEXT,
        "size_in_bytes": INTEGER,
        "checksum_algo": TEXT,
        "checksum_value": TEXT,
        "storage_backend": TEXT,
        "storage_key": NULLABLE_TEXT,
        "content_status": TEXT,
    },
    "event_history": {
        "id": INTEGER,
        "occurred_at": DATETIME,
        "transaction_id": INTEGER,
        "entity_type": TEXT,
        "entity_id": INTEGER,
        "operation": TEXT,
        "actor_user_id": NULLABLE_INTEGER,
        "actor_type": TEXT,
        "source": TEXT,
        "request_id": NULLABLE_UUID,
        "correlation_id": NULLABLE_UUID,
        "reason": NULLABLE_TEXT,
    },
    "org_units": {
        "id": INTEGER,
        "version": INTEGER,
        "parent_org_unit_id": NULLABLE_INTEGER,
        "code": TEXT,
        "name": TEXT,
        "description": NULLABLE_TEXT,
        "status": TEXT,
        "date_created": DATETIME,
        "date_deactivated": NULLABLE_DATETIME,
    },
    "users": {
        "id": INTEGER,
        "version": INTEGER,
        "name": TEXT,
        "email": NULLABLE_TEXT,
        "external_id": NULLABLE_TEXT,
        "account_type": TEXT,
        "status": TEXT,
        "date_created": DATETIME,
        "date_deactivated": NULLABLE_DATETIME,
    },
    "roles": {
        "id": INTEGER,
        "version": INTEGER,
        "org_unit_id": INTEGER,
        "supervisor_role_id": NULLABLE_INTEGER,
        "code": TEXT,
        "name": TEXT,
        "description": NULLABLE_TEXT,
        "status": TEXT,
        "date_created": DATETIME,
        "date_deactivated": NULLABLE_DATETIME,
    },
    "user_role_assignments": {
        "id": INTEGER,
        "version": INTEGER,
        "user_id": INTEGER,
        "role_id": INTEGER,
        "assigned_by": NULLABLE_INTEGER,
        "date_assigned": DATETIME,
        "valid_from": DATETIME,
        "valid_until": NULLABLE_DATETIME,
    },
}

SET_OPERATORS = {"in", "not_in"}
TEXT_OPERATORS = {"contains_ci", "starts_with_ci", "ends_with_ci"}
SIMPLE_SQL_OPERATORS = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=message)


def _coerce_value(field_name: str, field: SearchField, value: Any) -> Any:
    try:
        if field.type is FieldType.INTEGER:
            if isinstance(value, bool):
                raise ValueError
            return TypeAdapter(int).validate_python(value)
        if field.type is FieldType.TEXT:
            if not isinstance(value, str):
                raise ValueError
            return value
        if field.type is FieldType.UUID:
            return TypeAdapter(UUID).validate_python(value)
        parsed = TypeAdapter(datetime).validate_python(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (ValidationError, ValueError, TypeError) as exception:
        raise _invalid(f"invalid {field.type.value} value for field '{field_name}'") from exception


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _compile_comparison(
    expression: SearchExpression,
    fields: dict[str, SearchField],
) -> tuple[sql.Composable, list[Any]]:
    field_name = expression.field
    operator = expression.operator
    if field_name not in fields:
        raise _invalid(f"field '{field_name}' is not searchable")

    field = fields[field_name]
    identifier = sql.Identifier(field_name)

    if operator in TEXT_OPERATORS and field.type is not FieldType.TEXT:
        raise _invalid(f"operator '{operator}' is only valid for text fields")
    if operator in {"is_null", "is_not_null"} and not field.nullable:
        raise _invalid(f"field '{field_name}' is not nullable")

    if operator == "is_null":
        return sql.SQL("{} IS NULL").format(identifier), []
    if operator == "is_not_null":
        return sql.SQL("{} IS NOT NULL").format(identifier), []

    if operator in SET_OPERATORS:
        if not isinstance(expression.value, list):
            raise _invalid(f"operator '{operator}' requires an array value")
        if not expression.value or len(expression.value) > MAX_IN_VALUES:
            raise _invalid(f"operator '{operator}' requires 1 to {MAX_IN_VALUES} values")
        values = [_coerce_value(field_name, field, value) for value in expression.value]
        keyword = sql.SQL("IN") if operator == "in" else sql.SQL("NOT IN")
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in values)
        return sql.SQL("{} {} ({})").format(identifier, keyword, placeholders), values

    if operator == "between":
        if not isinstance(expression.value, list) or len(expression.value) != 2:
            raise _invalid("operator 'between' requires an array containing two values")
        values = [_coerce_value(field_name, field, value) for value in expression.value]
        return sql.SQL("{} BETWEEN %s AND %s").format(identifier), values

    if operator in TEXT_OPERATORS:
        value = _escape_like(_coerce_value(field_name, field, expression.value))
        if operator == "contains_ci":
            value = f"%{value}%"
        elif operator == "starts_with_ci":
            value = f"{value}%"
        else:
            value = f"%{value}"
        return sql.SQL("{} ILIKE %s ESCAPE '\\'").format(identifier), [value]

    if operator not in SIMPLE_SQL_OPERATORS:
        raise _invalid(f"operator '{operator}' is not supported")
    value = _coerce_value(field_name, field, expression.value)
    return sql.SQL("{} {} %s").format(
        identifier,
        sql.SQL(SIMPLE_SQL_OPERATORS[operator]),
    ), [value]


def _compile_expression(
    expression: SearchExpression,
    fields: dict[str, SearchField],
    *,
    depth: int,
    condition_counter: list[int],
) -> tuple[sql.Composable, list[Any]]:
    if depth > MAX_SEARCH_DEPTH:
        raise _invalid(f"search expressions may be nested at most {MAX_SEARCH_DEPTH} levels")

    if expression.field is not None:
        condition_counter[0] += 1
        if condition_counter[0] > MAX_SEARCH_CONDITIONS:
            raise _invalid(f"searches may contain at most {MAX_SEARCH_CONDITIONS} conditions")
        return _compile_comparison(expression, fields)

    if expression.not_ is not None:
        clause, parameters = _compile_expression(
            expression.not_, fields, depth=depth + 1, condition_counter=condition_counter
        )
        return sql.SQL("NOT ({})").format(clause), parameters

    children = expression.and_ if expression.and_ is not None else expression.or_
    joiner = sql.SQL(" AND ") if expression.and_ is not None else sql.SQL(" OR ")
    compiled = [
        _compile_expression(
            child, fields, depth=depth + 1, condition_counter=condition_counter
        )
        for child in children
    ]
    clauses = [clause for clause, _ in compiled]
    parameters = [value for _, values in compiled for value in values]
    return sql.SQL("({})").format(joiner.join(clauses)), parameters


def search_rows(
    connection: Connection,
    table: str,
    request: SearchRequest,
) -> dict[str, Any]:
    fields = SEARCH_FIELDS[table]
    where_clause = sql.SQL("")
    parameters: list[Any] = []
    if request.where is not None:
        expression, parameters = _compile_expression(
            request.where, fields, depth=1, condition_counter=[0]
        )
        where_clause = sql.SQL(" WHERE ") + expression

    sort_fields: list[tuple[str, str]] = []
    for item in request.sort:
        if item.field not in fields:
            raise _invalid(f"sort field '{item.field}' is not allowed")
        if item.field in {field for field, _ in sort_fields}:
            raise _invalid(f"sort field '{item.field}' is duplicated")
        sort_fields.append((item.field, item.direction))
    if not sort_fields:
        sort_fields.append(("id", "asc"))
    elif "id" not in {field for field, _ in sort_fields}:
        sort_fields.append(("id", "asc"))

    table_identifier = sql.Identifier(table)
    count_query = sql.SQL("SELECT count(*) AS total FROM {}{}").format(
        table_identifier, where_clause
    )
    total = connection.execute(count_query, parameters).fetchone()["total"]

    order_clause = sql.SQL(", ").join(
        sql.SQL("{} {}").format(sql.Identifier(field), sql.SQL(direction.upper()))
        for field, direction in sort_fields
    )
    result_query = sql.SQL("SELECT * FROM {}{} ORDER BY {} LIMIT %s OFFSET %s").format(
        table_identifier,
        where_clause,
        order_clause,
    )
    items = list(
        connection.execute(
            result_query, [*parameters, request.limit, request.offset]
        ).fetchall()
    )
    return {
        "items": items,
        "total": total,
        "limit": request.limit,
        "offset": request.offset,
        "returned": len(items),
    }
