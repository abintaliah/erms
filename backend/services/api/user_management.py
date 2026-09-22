import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from psycopg import Connection, sql

from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .concurrency import expected_version
from .database import get_connection
from .schemas import (
    EventHistoryRead,
    DeletionPreflightRead,
    OrgUnitCreate,
    OrgUnitRead,
    OrgUnitUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    ProfileRead,
    ProfileReferenceRead,
    SearchRequest,
    SearchResponse,
    UserCreate,
    UserRead,
    UserRoleAssignmentCreate,
    UserRoleAssignmentRead,
    UserRoleAssignmentUpdate,
    UserUpdate,
)
from .search import search_rows
from .authentication import revoke_sessions_for_user
from .security_level_events import append_security_level_event, validate_security_level_change
from .authorization_admin import (
    _effective_people_for_privilege, _reason, _universal_custodian_count,
    assert_continuity,
)
from .authorization_policy import (
    require_audit_view,
    require_identity_users_admin,
    require_organization_admin,
)
from .permanent_deletion import analyze_deletion, permanently_delete
from .continuity_lock import acquire_continuity_lock


router = APIRouter(prefix="/api/v1")


def _change_lifecycle(
    connection: Connection, table: str, entity_id: int, version: int,
    *, active: bool,
):
    return _update_lifecycle_dates(
        connection, table, entity_id, version,
        {"date_deactivated": "NULL" if active else "clock_timestamp()"},
    )


def _update_lifecycle_dates(
    connection: Connection,
    table: str,
    entity_id: int,
    version: int,
    assignments: dict[str, str],
):
    if table not in {"org_units", "users", "roles"}:
        raise ValueError("unsupported lifecycle table")
    allowed_columns = {"date_deactivated", "date_suspended"}
    if not assignments or not set(assignments).issubset(allowed_columns):
        raise ValueError("unsupported lifecycle assignment")
    allowed_expressions = {"NULL", "clock_timestamp()"}
    if not set(assignments.values()).issubset(allowed_expressions):
        raise ValueError("unsupported lifecycle expression")
    updates = sql.SQL(", ").join(
        sql.Identifier(column) + sql.SQL(" = ") + sql.SQL(expression)
        for column, expression in assignments.items()
    )
    query = sql.SQL(
        "UPDATE {} SET {} WHERE id = %s AND version = %s RETURNING *"
    ).format(sql.Identifier(table), updates)
    changed = connection.execute(query, (entity_id, version)).fetchone()
    if changed is None:
        current = get_or_404(connection, table, entity_id)
        raise HTTPException(
            status_code=412,
            detail={"message": "entity has changed", "current_version": current["version"]},
        )
    return changed


def _continuity_snapshot(connection: Connection) -> tuple[int, int]:
    return (
        _effective_people_for_privilege(connection, "authorization.administer"),
        _universal_custodian_count(connection),
    )


def _assert_snapshot_continuity(connection: Connection, snapshot: tuple[int, int]) -> None:
    assert_continuity(connection, snapshot[0], snapshot[1])


def _history(connection: Connection, entity_type: str, entity_id: int):
    return list_rows(
        connection,
        "event_history",
        limit=500,
        offset=0,
        filters={"entity_type": entity_type, "entity_id": entity_id},
        order_by=("occurred_at", "id"),
        descending=True,
    )


@router.get("/profiles/reference", response_model=list[ProfileReferenceRead], tags=["profiles"])
def list_profile_references(
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    """Profile identity and unrestricted-profile warning state for role selectors."""
    return list(connection.execute(
        """SELECT profile.*,
                  ((SELECT count(*) FROM profile_privileges membership
                     WHERE membership.profile_id=profile.id)
                   = (SELECT count(*) FROM privileges)
                   AND (SELECT count(*) FROM privileges)>0) AS grants_all_privileges
             FROM profiles profile
            ORDER BY profile.name,profile.id LIMIT %s OFFSET %s""",
        (limit, offset),
    ).fetchall())


@router.post("/org-units", response_model=OrgUnitRead, status_code=201, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def create_org_unit(payload: OrgUnitCreate, connection: Connection = Depends(get_connection, scope="function")):
    return create_row(connection, "org_units", payload.model_dump())


@router.get("/org-units", response_model=list[OrgUnitRead], tags=["org units"])
def list_org_units(
    parent_org_unit_id: int | None = None,
    unit_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "org_units",
        limit=limit,
        offset=offset,
        filters={"parent_org_unit_id": parent_org_unit_id, "status": unit_status},
    )


@router.post("/org-units/search", response_model=SearchResponse[OrgUnitRead], tags=["org units"])
def search_org_units(payload: SearchRequest, connection: Connection = Depends(get_connection, scope="function")):
    return search_rows(connection, "org_units", payload)


@router.get("/org-units/{org_unit_id}", response_model=OrgUnitRead, tags=["org units"])
def get_org_unit(org_unit_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "org_units", org_unit_id)


@router.get("/org-units/{org_unit_id}/deletion-preflight", response_model=DeletionPreflightRead, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def preflight_org_unit_deletion(request: Request, org_unit_id: int, connection: Connection = Depends(get_connection, scope="function")):
    principal = getattr(request.state, "principal", None)
    return analyze_deletion(connection, "org_unit", org_unit_id, actor_user_id=principal.user_id if principal else None)


@router.delete("/org-units/{org_unit_id}", status_code=204, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def permanently_delete_org_unit(request: Request, org_unit_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    permanently_delete(connection, request, "org_unit", org_unit_id, version)
    return Response(status_code=204)


@router.patch("/org-units/{org_unit_id}", response_model=OrgUnitRead, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def update_org_unit(
    org_unit_id: int,
    payload: OrgUnitUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    changed = update_row(
        connection, "org_units", org_unit_id, payload.model_dump(exclude_unset=True), version
    )
    _assert_snapshot_continuity(connection, snapshot)
    return changed


@router.post("/org-units/{org_unit_id}/deactivate", response_model=OrgUnitRead, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def explicitly_deactivate_org_unit(org_unit_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    changed = _change_lifecycle(connection, "org_units", org_unit_id, version, active=False)
    _assert_snapshot_continuity(connection, snapshot)
    return changed


@router.post("/org-units/{org_unit_id}/activate", response_model=OrgUnitRead, tags=["org units"], dependencies=[Depends(require_organization_admin)])
def activate_org_unit(org_unit_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _change_lifecycle(connection, "org_units", org_unit_id, version, active=True)


@router.get(
    "/org-units/{org_unit_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_org_unit_history(org_unit_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return _history(connection, "org_unit", org_unit_id)


@router.post("/users", response_model=UserRead, status_code=201, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def create_user(payload: UserCreate, connection: Connection = Depends(get_connection, scope="function")):
    return create_row(connection, "users", payload.model_dump())


@router.get("/users", response_model=list[UserRead], tags=["users"])
def list_users(
    user_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "users",
        limit=limit,
        offset=offset,
        filters={"status": user_status},
    )


@router.post("/users/search", response_model=SearchResponse[UserRead], tags=["users"])
def search_users(payload: SearchRequest, connection: Connection = Depends(get_connection, scope="function")):
    return search_rows(connection, "users", payload)


@router.get("/users/{user_id}", response_model=UserRead, tags=["users"])
def get_user(user_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "users", user_id)


@router.get("/users/{user_id}/deletion-preflight", response_model=DeletionPreflightRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def preflight_user_deletion(request: Request, user_id: int, connection: Connection = Depends(get_connection, scope="function")):
    principal = getattr(request.state, "principal", None)
    return analyze_deletion(connection, "user", user_id, actor_user_id=principal.user_id if principal else None)


@router.delete("/users/{user_id}", status_code=204, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def permanently_delete_user(request: Request, user_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    permanently_delete(connection, request, "user", user_id, version)
    return Response(status_code=204)


@router.patch("/users/{user_id}", response_model=UserRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def update_user(
    user_id: int,
    payload: UserUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    changed = update_row(connection, "users", user_id, payload.model_dump(exclude_unset=True), version)
    _assert_snapshot_continuity(connection, snapshot)
    return changed


def _set_user_lifecycle(
    connection: Connection,
    request: Request,
    user_id: int,
    version: int,
    *,
    action: str,
):
    acquire_continuity_lock(connection)
    current = get_or_404(connection, "users", user_id)
    continuity_snapshot = _continuity_snapshot(connection)
    transitions = {
        "activate": ({"inactive"}, "active", None),
        "deactivate": ({"active", "suspended"}, "inactive", "user_deactivated"),
        "suspend": ({"active"}, "suspended", "user_suspended"),
        "unsuspend": ({"suspended"}, "active", None),
    }
    allowed, target_status, revocation_reason = transitions[action]
    if current["status"] not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"cannot {action} a user whose status is {current['status']}",
        )
    if target_status == "inactive":
        values = {
            "date_deactivated": "clock_timestamp()",
            "date_suspended": "NULL",
        }
    elif target_status == "suspended":
        values = {
            "date_deactivated": "NULL",
            "date_suspended": "clock_timestamp()",
        }
    else:
        values = {"date_deactivated": "NULL", "date_suspended": "NULL"}
    changed = _update_lifecycle_dates(
        connection, "users", user_id, version, values,
    )
    if revocation_reason:
        principal = getattr(request.state, "principal", None)
        revoke_sessions_for_user(
            connection,
            user_id,
            revoked_by=principal.user_id if principal else None,
            reason=revocation_reason,
        )
    _assert_snapshot_continuity(connection, continuity_snapshot)
    return changed


@router.post("/users/{user_id}/deactivate", response_model=UserRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def explicitly_deactivate_user(request: Request, user_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _set_user_lifecycle(connection, request, user_id, version, action="deactivate")


@router.post("/users/{user_id}/activate", response_model=UserRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def activate_user(request: Request, user_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _set_user_lifecycle(connection, request, user_id, version, action="activate")


@router.post("/users/{user_id}/suspend", response_model=UserRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def suspend_user(request: Request, user_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _set_user_lifecycle(connection, request, user_id, version, action="suspend")


@router.post("/users/{user_id}/unsuspend", response_model=UserRead, tags=["users"], dependencies=[Depends(require_identity_users_admin)])
def unsuspend_user(request: Request, user_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _set_user_lifecycle(connection, request, user_id, version, action="unsuspend")


@router.get(
    "/users/{user_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_user_history(user_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return _history(connection, "user", user_id)


@router.post("/roles", response_model=RoleRead, status_code=201, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def create_role(payload: RoleCreate, connection: Connection = Depends(get_connection, scope="function")):
    return create_row(connection, "roles", payload.model_dump())


@router.get("/roles", response_model=list[RoleRead], tags=["roles"])
def list_roles(
    org_unit_id: int | None = None,
    supervisor_role_id: int | None = None,
    role_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "roles",
        limit=limit,
        offset=offset,
        filters={
            "org_unit_id": org_unit_id,
            "supervisor_role_id": supervisor_role_id,
            "status": role_status,
        },
    )


@router.post("/roles/search", response_model=SearchResponse[RoleRead], tags=["roles"])
def search_roles(payload: SearchRequest, connection: Connection = Depends(get_connection, scope="function")):
    return search_rows(connection, "roles", payload)


@router.get("/roles/{role_id}", response_model=RoleRead, tags=["roles"])
def get_role(role_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "roles", role_id)


@router.get("/roles/{role_id}/deletion-preflight", response_model=DeletionPreflightRead, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def preflight_role_deletion(request: Request, role_id: int, connection: Connection = Depends(get_connection, scope="function")):
    principal = getattr(request.state, "principal", None)
    return analyze_deletion(connection, "role", role_id, actor_user_id=principal.user_id if principal else None)


@router.delete("/roles/{role_id}", status_code=204, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def permanently_delete_role(request: Request, role_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    permanently_delete(connection, request, "role", role_id, version)
    return Response(status_code=204)


@router.patch("/roles/{role_id}", response_model=RoleRead, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def update_role(
    role_id: int,
    payload: RoleUpdate,
    request: Request,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    existing = get_or_404(connection, "roles", role_id)
    sensitive_authorization_change = (
        "profile_id" in payload.model_fields_set
        and payload.profile_id != existing["profile_id"]
    ) or (
        "is_information_governance" in payload.model_fields_set
        and payload.is_information_governance != existing["is_information_governance"]
    )
    clearance_change = (
        "security_level_id" in payload.model_fields_set
        and payload.security_level_id != existing["security_level_id"]
    )
    authorization_reason = _reason(request) if sensitive_authorization_change else None
    continuity_snapshot = (
        _continuity_snapshot(connection)
        if sensitive_authorization_change or clearance_change
        else None
    )
    new_level_id = payload.security_level_id if "security_level_id" in payload.model_fields_set else None
    reason, old_number, new_number = validate_security_level_change(
        connection, request, existing["security_level_id"], new_level_id
    )
    updated = update_row(connection, "roles", role_id, payload.model_dump(exclude_unset=True), version)
    append_security_level_event(
        connection, entity_type="role", entity_id=role_id,
        old_security_level_id=existing["security_level_id"], new_security_level_id=new_level_id,
        old_level_number=old_number, new_level_number=new_number, reason=reason,
    )
    if continuity_snapshot is not None:
        _assert_snapshot_continuity(connection, continuity_snapshot)
    if "profile_id" in payload.model_fields_set and payload.profile_id != existing["profile_id"]:
        connection.execute(
            "SELECT append_domain_event('role',%s,'PROFILE_ASSIGNED',%s::jsonb,%s)",
            (role_id, json.dumps({
                "old_profile_id": existing["profile_id"], "new_profile_id": payload.profile_id,
            }), authorization_reason),
        )
    if "is_information_governance" in payload.model_fields_set and payload.is_information_governance != existing["is_information_governance"]:
        connection.execute(
            "SELECT append_domain_event('role',%s,'GOVERNANCE_ROLE_CHANGED',%s::jsonb,%s)",
            (role_id, json.dumps({
                "old_value": existing["is_information_governance"],
                "new_value": payload.is_information_governance,
            }), authorization_reason),
        )
    return updated


@router.post("/roles/{role_id}/deactivate", response_model=RoleRead, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def explicitly_deactivate_role(role_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    changed = _change_lifecycle(connection, "roles", role_id, version, active=False)
    _assert_snapshot_continuity(connection, snapshot)
    return changed


@router.post("/roles/{role_id}/activate", response_model=RoleRead, tags=["roles"], dependencies=[Depends(require_organization_admin)])
def activate_role(role_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    return _change_lifecycle(connection, "roles", role_id, version, active=True)


@router.get(
    "/roles/{role_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_role_history(role_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return _history(connection, "role", role_id)


@router.post(
    "/user-role-assignments",
    response_model=UserRoleAssignmentRead,
    status_code=201,
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def create_assignment(
    payload: UserRoleAssignmentCreate,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return create_row(connection, "user_role_assignments", payload.model_dump())


@router.get(
    "/user-role-assignments",
    response_model=list[UserRoleAssignmentRead],
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def list_assignments(
    user_id: int | None = None,
    role_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "user_role_assignments",
        limit=limit,
        offset=offset,
        filters={"user_id": user_id, "role_id": role_id},
    )


@router.post(
    "/user-role-assignments/search",
    response_model=SearchResponse[UserRoleAssignmentRead],
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def search_assignments(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return search_rows(connection, "user_role_assignments", payload)


@router.get(
    "/user-role-assignments/{assignment_id}",
    response_model=UserRoleAssignmentRead,
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def get_assignment(assignment_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "user_role_assignments", assignment_id)


@router.patch(
    "/user-role-assignments/{assignment_id}",
    response_model=UserRoleAssignmentRead,
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def update_assignment(
    assignment_id: int,
    payload: UserRoleAssignmentUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    changed = update_row(
        connection,
        "user_role_assignments",
        assignment_id,
        payload.model_dump(exclude_unset=True),
        version,
    )
    _assert_snapshot_continuity(connection, snapshot)
    return changed


@router.delete(
    "/user-role-assignments/{assignment_id}",
    status_code=204,
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def delete_assignment(assignment_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    acquire_continuity_lock(connection)
    snapshot = _continuity_snapshot(connection)
    delete_row(connection, "user_role_assignments", assignment_id, version)
    _assert_snapshot_continuity(connection, snapshot)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/user-role-assignments/{assignment_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_assignment_history(
    assignment_id: int,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return _history(connection, "user_role_assignment", assignment_id)


@router.get(
    "/users/{user_id}/roles",
    response_model=list[UserRoleAssignmentRead],
    tags=["user role assignments"],
    dependencies=[Depends(require_identity_users_admin)],
)
def get_user_roles(user_id: int, connection: Connection = Depends(get_connection, scope="function")):
    get_or_404(connection, "users", user_id)
    return list_rows(
        connection,
        "user_role_assignments",
        limit=500,
        offset=0,
        filters={"user_id": user_id},
    )


@router.get(
    "/roles/{role_id}/users",
    response_model=list[UserRoleAssignmentRead],
    tags=["user role assignments"],
    dependencies=[Depends(require_organization_admin)],
)
def get_role_users(role_id: int, connection: Connection = Depends(get_connection, scope="function")):
    get_or_404(connection, "roles", role_id)
    return list_rows(
        connection,
        "user_role_assignments",
        limit=500,
        offset=0,
        filters={"role_id": role_id},
    )
