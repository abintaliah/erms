from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from psycopg import Connection


def level_number(connection: Connection, security_level_id: int) -> int:
    row = connection.execute(
        "SELECT level_number FROM security_levels WHERE id=%s", (security_level_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=422, detail="security level not found")
    return row["level_number"]


def validate_security_level_change(
    connection: Connection,
    request: Request,
    old_security_level_id: int,
    new_security_level_id: int | None,
) -> tuple[str | None, int, int]:
    if new_security_level_id is None or new_security_level_id == old_security_level_id:
        return None, level_number(connection, old_security_level_id), level_number(connection, old_security_level_id)
    old_number = level_number(connection, old_security_level_id)
    new_number = level_number(connection, new_security_level_id)
    reason = request.headers.get("X-Change-Reason", "").strip() or None
    if new_number < old_number and reason is None:
        raise HTTPException(
            status_code=422,
            detail="X-Change-Reason is required when lowering a security level",
        )
    return reason, old_number, new_number


def append_security_level_event(
    connection: Connection,
    *,
    entity_type: str,
    entity_id: int,
    old_security_level_id: int,
    new_security_level_id: int | None,
    old_level_number: int,
    new_level_number: int,
    reason: str | None,
    remedy: str | None = None,
) -> None:
    if new_security_level_id is None or new_security_level_id == old_security_level_id:
        return
    operation = "ROLE_SECURITY_CLEARANCE_CHANGED" if entity_type == "role" else (
        "SECURITY_LEVEL_UPGRADED" if new_level_number > old_level_number
        else "SECURITY_LEVEL_DOWNGRADED"
    )
    connection.execute(
        "SELECT append_domain_event(%s,%s,%s,%s::jsonb,%s)",
        (
            entity_type,
            entity_id,
            operation,
            json.dumps({
                "old_security_level_id": old_security_level_id,
                "new_security_level_id": new_security_level_id,
                "old_level_number": old_level_number,
                "new_level_number": new_level_number,
                "remedy": remedy,
            }),
            reason,
        ),
    )
