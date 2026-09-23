from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from psycopg import Connection

from .concurrency import expected_version
from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .database import get_connection
from .schemas import (
    EventHistoryRead,
    SecurityLevelChangeApplyRequest,
    SecurityLevelChangePreviewRead,
    SecurityLevelChangePreviewRequest,
    SecurityLevelCreate,
    SecurityLevelRead,
    SecurityLevelUpdate,
)
from .security_level_events import append_security_level_event
from .continuity_lock import acquire_continuity_lock
from .authorization_admin import (
    _effective_people_for_privilege,
    _universal_custodian_count,
    assert_continuity,
)


def _continuity_snapshot(connection: Connection) -> tuple[int, int]:
    return (
        _effective_people_for_privilege(connection, "authorization.administer"),
        _universal_custodian_count(connection),
    )
from .authorization_policy import require_audit_view, require_security_levels_admin
from .resource_authorization import (
    require_clearance_for_level, require_global, require_resource_operation,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["security levels"],
)
_PREVIEW_SECRET = secrets.token_bytes(32)


def _level(connection: Connection, level_id: int) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM security_levels WHERE id=%s", (level_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="security level not found")
    return row


def _resource(connection: Connection, kind: str, resource_id: int) -> dict[str, Any]:
    table = "aggregations" if kind == "aggregation" else "records"
    row = connection.execute(f"SELECT * FROM {table} WHERE id=%s", (resource_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{kind} not found")
    return row


def _ancestors(connection: Connection, aggregation_id: int | None) -> list[dict[str, Any]]:
    if aggregation_id is None:
        return []
    return list(connection.execute(
        """
        WITH RECURSIVE ancestors AS (
            SELECT a.id,a.parent_aggregation_id,a.security_level_id,a.version,0 depth
            FROM aggregations a WHERE a.id=%s
            UNION ALL
            SELECT parent.id,parent.parent_aggregation_id,parent.security_level_id,parent.version,child.depth+1
            FROM aggregations parent JOIN ancestors child ON parent.id=child.parent_aggregation_id
        )
        SELECT ancestors.*,level.level_number FROM ancestors
        JOIN security_levels level ON level.id=ancestors.security_level_id
        ORDER BY depth DESC,id
        """, (aggregation_id,)
    ).fetchall())


def _subtree_above(connection: Connection, aggregation_id: int, target: int) -> tuple[list[dict], list[dict]]:
    aggregations = list(connection.execute(
        """
        WITH RECURSIVE tree AS (
            SELECT id,parent_aggregation_id,security_level_id,version,0 depth
            FROM aggregations WHERE id=%s
            UNION ALL
            SELECT child.id,child.parent_aggregation_id,child.security_level_id,child.version,parent.depth+1
            FROM aggregations child JOIN tree parent ON child.parent_aggregation_id=parent.id
        )
        SELECT tree.*,level.level_number FROM tree
        JOIN security_levels level ON level.id=tree.security_level_id
        WHERE level.level_number>%s ORDER BY depth DESC,id
        """, (aggregation_id, target)
    ).fetchall())
    records = list(connection.execute(
        """
        WITH RECURSIVE tree AS (
            SELECT id FROM aggregations WHERE id=%s
            UNION ALL SELECT child.id FROM aggregations child JOIN tree parent ON child.parent_aggregation_id=parent.id
        )
        SELECT record.id,record.aggregation_id,record.security_level_id,record.version,level.level_number
        FROM records record JOIN tree ON tree.id=record.aggregation_id
        JOIN security_levels level ON level.id=record.security_level_id
        WHERE level.level_number>%s ORDER BY record.id
        """, (aggregation_id, target)
    ).fetchall())
    return aggregations, records


def _unsigned_payload(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def _sign(data: dict[str, Any]) -> str:
    body = _unsigned_payload(data)
    signature = hmac.new(_PREVIEW_SECRET, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def _verify(token: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        body, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.new(_PREVIEW_SECRET, body, hashlib.sha256).digest()):
            raise ValueError
        return json.loads(body)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=409, detail="invalid or expired security-level preview") from error


def _build_preview(connection: Connection, request: SecurityLevelChangePreviewRequest) -> dict[str, Any]:
    target = _level(connection, request.target_security_level_id)
    resource = _resource(connection, request.resource_type, request.resource_id)
    if request.resource_type == "aggregation":
        parent_id = request.destination_aggregation_id if request.destination_aggregation_id is not None else resource["parent_aggregation_id"]
    else:
        parent_id = request.destination_aggregation_id if request.destination_aggregation_id is not None else resource["aggregation_id"]
    ancestors = _ancestors(connection, parent_id)
    low_ancestors = [item for item in ancestors if item["level_number"] < target["level_number"]]
    subtree_aggregations: list[dict] = []
    subtree_records: list[dict] = []
    if request.resource_type == "aggregation":
        subtree_aggregations, subtree_records = _subtree_above(
            connection, request.resource_id, target["level_number"]
        )
    conflict = bool(low_ancestors or subtree_aggregations or subtree_records)
    affected_aggregations: list[dict] = []
    affected_records: list[dict] = []
    if request.remedy == "raise_ancestors":
        affected_aggregations = low_ancestors
    elif request.remedy == "downgrade_subtree":
        affected_aggregations = subtree_aggregations
        affected_records = subtree_records
    versions = {
        "resource": resource["version"],
        "aggregations": {str(row["id"]): row["version"] for row in affected_aggregations},
        "records": {str(row["id"]): row["version"] for row in affected_records},
    }
    request_data = request.model_dump()
    payload = {"request": request_data, "versions": versions}
    return {
        "preview_token": _sign(payload),
        "conflict": conflict,
        "remedy": request.remedy,
        "target_level_number": target["level_number"],
        "affected_aggregations": affected_aggregations,
        "affected_records": affected_records,
        "_payload": payload,
    }


@router.post("/security-levels", response_model=SecurityLevelRead, status_code=201, dependencies=[Depends(require_security_levels_admin)])
def create_security_level(payload: SecurityLevelCreate, connection: Connection = Depends(get_connection, scope="function")):
    acquire_continuity_lock(connection)
    before = _continuity_snapshot(connection)
    created = create_row(connection, "security_levels", payload.model_dump())
    assert_continuity(connection, *before)
    return created


@router.get("/security-levels", response_model=list[SecurityLevelRead])
def list_security_levels(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list(connection.execute(
        """SELECT level.*,
                  (SELECT count(*) FROM roles role WHERE role.security_level_id=level.id) roles_assigned_count,
                  (SELECT count(*) FROM aggregations aggregation WHERE aggregation.security_level_id=level.id) aggregation_count,
                  (SELECT count(*) FROM records record WHERE record.security_level_id=level.id) record_count
             FROM security_levels level ORDER BY level.level_number,level.id LIMIT %s OFFSET %s""",
        (limit, offset)
    ).fetchall())


@router.get("/security-levels/{level_id}", response_model=SecurityLevelRead)
def get_security_level(level_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "security_levels", level_id)


@router.get(
    "/security-levels/{level_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_security_level_history(
    level_id: int, connection: Connection=Depends(get_connection, scope="function"),
):
    get_or_404(connection, "security_levels", level_id)
    return list_rows(
        connection, "event_history", limit=500, offset=0,
        filters={"entity_type": "security_level", "entity_id": level_id},
        order_by=("occurred_at", "id"), descending=True,
    )


@router.patch("/security-levels/{level_id}", response_model=SecurityLevelRead, dependencies=[Depends(require_security_levels_admin)])
def update_security_level(
    level_id: int, payload: SecurityLevelUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    before = _continuity_snapshot(connection)
    updated = update_row(connection, "security_levels", level_id, payload.model_dump(exclude_unset=True), version)
    assert_continuity(connection, *before)
    return updated


@router.delete("/security-levels/{level_id}", status_code=204, dependencies=[Depends(require_security_levels_admin)])
def delete_security_level(
    level_id: int, version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    before = _continuity_snapshot(connection)
    baseline = connection.execute(
        "SELECT lowest_security_level_id() AS id"
    ).fetchone()["id"]
    if level_id == baseline:
        raise HTTPException(status_code=409, detail="the baseline security level cannot be deleted")
    delete_row(connection, "security_levels", level_id, version)
    assert_continuity(connection, *before)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/security-level-changes/preview", response_model=SecurityLevelChangePreviewRead)
def preview_security_level_change(
    payload: SecurityLevelChangePreviewRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    privilege = f"{payload.resource_type}.security_level.change"
    require_resource_operation(
        connection, payload.resource_type, payload.resource_id,
        privilege, privilege, lock=False,
    )
    if payload.destination_aggregation_id is not None:
        source_permission = f"{payload.resource_type}.move"
        receive_permission = (
            "aggregation.receive_child" if payload.resource_type == "aggregation"
            else "aggregation.receive_record"
        )
        require_resource_operation(
            connection, payload.resource_type, payload.resource_id,
            source_permission, source_permission, lock=False,
        )
        require_resource_operation(
            connection, "aggregation", payload.destination_aggregation_id,
            source_permission, receive_permission, lock=False,
        )
    preview = _build_preview(connection, payload)
    preview.pop("_payload", None)
    return preview


@router.post("/security-level-changes/apply")
def apply_security_level_change(
    payload: SecurityLevelChangeApplyRequest,
    request: Request,
    connection: Connection = Depends(get_connection, scope="function"),
):
    reason = request.headers.get("X-Change-Reason", "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="X-Change-Reason is required")
    original = _verify(payload.preview_token)
    preview_request = SecurityLevelChangePreviewRequest(**payload.model_dump(exclude={"preview_token"}))
    if original["request"] != preview_request.model_dump():
        raise HTTPException(status_code=409, detail="security-level preview does not match request")
    current = _build_preview(connection, preview_request)
    if current["_payload"]["versions"] != original["versions"]:
        raise HTTPException(status_code=412, detail="security-level preview is stale")
    if current["conflict"] and payload.remedy == "none":
        raise HTTPException(status_code=409, detail="security_hierarchy_violation")
    target_id = payload.target_security_level_id
    require_clearance_for_level(connection, target_id)
    privilege = f"{payload.resource_type}.security_level.change"
    require_resource_operation(
        connection, payload.resource_type, payload.resource_id,
        privilege, privilege,
    )
    if payload.destination_aggregation_id is not None:
        source_permission = f"{payload.resource_type}.move"
        receive_permission = (
            "aggregation.receive_child" if payload.resource_type == "aggregation"
            else "aggregation.receive_record"
        )
        require_resource_operation(
            connection, payload.resource_type, payload.resource_id,
            source_permission, source_permission,
        )
        require_resource_operation(
            connection, "aggregation", payload.destination_aggregation_id,
            source_permission, receive_permission,
        )
    for row in current["affected_aggregations"]:
        require_resource_operation(
            connection, "aggregation", row["id"],
            "aggregation.security_level.change", "aggregation.security_level.change",
        )
    for row in current["affected_records"]:
        require_resource_operation(
            connection, "record", row["id"],
            "record.security_level.change", "record.security_level.change",
        )
    resource = _resource(connection, payload.resource_type, payload.resource_id)
    old_level = _level(connection, resource["security_level_id"])
    target_level = _level(connection, target_id)
    if target_level["level_number"] < old_level["level_number"]:
        require_global(connection, "security.resource.downgrade")
    for row in current["affected_records"]:
        connection.execute("UPDATE records SET security_level_id=%s WHERE id=%s", (target_id, row["id"]))
    for row in current["affected_aggregations"]:
        if payload.resource_type == "aggregation" and row["id"] == payload.resource_id:
            continue
        connection.execute("UPDATE aggregations SET security_level_id=%s WHERE id=%s", (target_id, row["id"]))
    table = "aggregations" if payload.resource_type == "aggregation" else "records"
    parent_column = "parent_aggregation_id" if payload.resource_type == "aggregation" else "aggregation_id"
    assignments = ["security_level_id=%s"]
    parameters: list[Any] = [target_id]
    if payload.destination_aggregation_id is not None:
        assignments.append(f"{parent_column}=%s")
        parameters.append(payload.destination_aggregation_id)
    parameters.append(payload.resource_id)
    connection.execute(f"UPDATE {table} SET {','.join(assignments)} WHERE id=%s", parameters)
    append_security_level_event(
        connection,
        entity_type=payload.resource_type,
        entity_id=payload.resource_id,
        old_security_level_id=resource["security_level_id"],
        new_security_level_id=target_id,
        old_level_number=old_level["level_number"],
        new_level_number=target_level["level_number"],
        reason=reason,
        remedy=payload.remedy,
    )
    return {"status": "applied", "resource": _resource(connection, payload.resource_type, payload.resource_id)}
