from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from psycopg import Connection

from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .database import get_connection
from .schemas import (
    EventHistoryRead,
    OrgUnitCreate,
    OrgUnitRead,
    OrgUnitUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
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


router = APIRouter(prefix="/api/v1")


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


@router.post("/org-units", response_model=OrgUnitRead, status_code=201, tags=["org units"])
def create_org_unit(payload: OrgUnitCreate, connection: Connection = Depends(get_connection)):
    return create_row(connection, "org_units", payload.model_dump())


@router.get("/org-units", response_model=list[OrgUnitRead], tags=["org units"])
def list_org_units(
    parent_org_unit_id: int | None = None,
    unit_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "org_units",
        limit=limit,
        offset=offset,
        filters={"parent_org_unit_id": parent_org_unit_id, "status": unit_status},
    )


@router.post("/org-units/search", response_model=SearchResponse[OrgUnitRead], tags=["org units"])
def search_org_units(payload: SearchRequest, connection: Connection = Depends(get_connection)):
    return search_rows(connection, "org_units", payload)


@router.get("/org-units/{org_unit_id}", response_model=OrgUnitRead, tags=["org units"])
def get_org_unit(org_unit_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "org_units", org_unit_id)


@router.patch("/org-units/{org_unit_id}", response_model=OrgUnitRead, tags=["org units"])
def update_org_unit(
    org_unit_id: int,
    payload: OrgUnitUpdate,
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection, "org_units", org_unit_id, payload.model_dump(exclude_unset=True)
    )


@router.delete("/org-units/{org_unit_id}", status_code=204, tags=["org units"])
def deactivate_org_unit(org_unit_id: int, connection: Connection = Depends(get_connection)):
    update_row(
        connection,
        "org_units",
        org_unit_id,
        {"status": "inactive", "date_closed": datetime.now(timezone.utc)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/org-units/{org_unit_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_org_unit_history(org_unit_id: int, connection: Connection = Depends(get_connection)):
    return _history(connection, "org_unit", org_unit_id)


@router.post("/users", response_model=UserRead, status_code=201, tags=["users"])
def create_user(payload: UserCreate, connection: Connection = Depends(get_connection)):
    return create_row(connection, "users", payload.model_dump())


@router.get("/users", response_model=list[UserRead], tags=["users"])
def list_users(
    user_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
):
    return list_rows(
        connection,
        "users",
        limit=limit,
        offset=offset,
        filters={"status": user_status},
    )


@router.post("/users/search", response_model=SearchResponse[UserRead], tags=["users"])
def search_users(payload: SearchRequest, connection: Connection = Depends(get_connection)):
    return search_rows(connection, "users", payload)


@router.get("/users/{user_id}", response_model=UserRead, tags=["users"])
def get_user(user_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "users", user_id)


@router.patch("/users/{user_id}", response_model=UserRead, tags=["users"])
def update_user(
    user_id: int,
    payload: UserUpdate,
    connection: Connection = Depends(get_connection),
):
    return update_row(connection, "users", user_id, payload.model_dump(exclude_unset=True))


@router.delete("/users/{user_id}", status_code=204, tags=["users"])
def deactivate_user(user_id: int, connection: Connection = Depends(get_connection)):
    update_row(
        connection,
        "users",
        user_id,
        {"status": "inactive", "date_deactivated": datetime.now(timezone.utc)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/users/{user_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_user_history(user_id: int, connection: Connection = Depends(get_connection)):
    return _history(connection, "user", user_id)


@router.post("/roles", response_model=RoleRead, status_code=201, tags=["roles"])
def create_role(payload: RoleCreate, connection: Connection = Depends(get_connection)):
    return create_row(connection, "roles", payload.model_dump())


@router.get("/roles", response_model=list[RoleRead], tags=["roles"])
def list_roles(
    org_unit_id: int | None = None,
    supervisor_role_id: int | None = None,
    role_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
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
def search_roles(payload: SearchRequest, connection: Connection = Depends(get_connection)):
    return search_rows(connection, "roles", payload)


@router.get("/roles/{role_id}", response_model=RoleRead, tags=["roles"])
def get_role(role_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "roles", role_id)


@router.patch("/roles/{role_id}", response_model=RoleRead, tags=["roles"])
def update_role(
    role_id: int,
    payload: RoleUpdate,
    connection: Connection = Depends(get_connection),
):
    return update_row(connection, "roles", role_id, payload.model_dump(exclude_unset=True))


@router.delete("/roles/{role_id}", status_code=204, tags=["roles"])
def deactivate_role(role_id: int, connection: Connection = Depends(get_connection)):
    update_row(
        connection,
        "roles",
        role_id,
        {"status": "inactive", "date_deactivated": datetime.now(timezone.utc)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/roles/{role_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_role_history(role_id: int, connection: Connection = Depends(get_connection)):
    return _history(connection, "role", role_id)


@router.post(
    "/user-role-assignments",
    response_model=UserRoleAssignmentRead,
    status_code=201,
    tags=["user role assignments"],
)
def create_assignment(
    payload: UserRoleAssignmentCreate,
    connection: Connection = Depends(get_connection),
):
    return create_row(connection, "user_role_assignments", payload.model_dump())


@router.get(
    "/user-role-assignments",
    response_model=list[UserRoleAssignmentRead],
    tags=["user role assignments"],
)
def list_assignments(
    user_id: int | None = None,
    role_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection),
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
)
def search_assignments(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection),
):
    return search_rows(connection, "user_role_assignments", payload)


@router.get(
    "/user-role-assignments/{assignment_id}",
    response_model=UserRoleAssignmentRead,
    tags=["user role assignments"],
)
def get_assignment(assignment_id: int, connection: Connection = Depends(get_connection)):
    return get_or_404(connection, "user_role_assignments", assignment_id)


@router.patch(
    "/user-role-assignments/{assignment_id}",
    response_model=UserRoleAssignmentRead,
    tags=["user role assignments"],
)
def update_assignment(
    assignment_id: int,
    payload: UserRoleAssignmentUpdate,
    connection: Connection = Depends(get_connection),
):
    return update_row(
        connection,
        "user_role_assignments",
        assignment_id,
        payload.model_dump(exclude_unset=True),
    )


@router.delete(
    "/user-role-assignments/{assignment_id}",
    status_code=204,
    tags=["user role assignments"],
)
def delete_assignment(assignment_id: int, connection: Connection = Depends(get_connection)):
    delete_row(connection, "user_role_assignments", assignment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/user-role-assignments/{assignment_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_assignment_history(
    assignment_id: int,
    connection: Connection = Depends(get_connection),
):
    return _history(connection, "user_role_assignment", assignment_id)


@router.get(
    "/users/{user_id}/roles",
    response_model=list[UserRoleAssignmentRead],
    tags=["user role assignments"],
)
def get_user_roles(user_id: int, connection: Connection = Depends(get_connection)):
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
)
def get_role_users(role_id: int, connection: Connection = Depends(get_connection)):
    get_or_404(connection, "roles", role_id)
    return list_rows(
        connection,
        "user_role_assignments",
        limit=500,
        offset=0,
        filters={"role_id": role_id},
    )
