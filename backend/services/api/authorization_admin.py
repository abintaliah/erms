from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from psycopg import Connection

from .concurrency import expected_version
from .crud import create_row, delete_row, get_or_404, update_row
from .database import get_connection
from .authorization_policy import require_authorization_admin
from .continuity_lock import acquire_continuity_lock
from .schemas import (
    PrivilegeRead, ProfileCreate, ProfilePrivilegeReplace, ProfileRead,
    ProfileUpdate, RoleProfileAssignment, RoleRead,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["authorization administration"],
    dependencies=[Depends(require_authorization_admin)],
)

CUSTODY_PRIVILEGE_CODES = (
    "authorization.administer", "authorization.explain", "audit.view",
    "aggregation.view", "aggregation.create_root", "aggregation.create_child",
    "aggregation.modify", "aggregation.move", "aggregation.reclassify",
    "aggregation.close", "aggregation.reopen", "aggregation.delete",
    "aggregation.security_level.change", "aggregation.acl.manage",
    "record.view", "record.create", "record.modify", "record.move",
    "record.delete", "record.security_level.change", "record.acl.manage",
    "record.component.view", "record.component.download", "record.component.add",
    "record.component.replace", "record.component.remove", "record.component.reorder",
    "record.component.share", "record.component.print", "security.resource.downgrade",
    "closure.correct_record_placement",
)


def _reason(request: Request) -> str:
    reason = request.headers.get("X-Change-Reason", "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="X-Change-Reason is required")
    return reason


def _impact(connection: Connection, profile_id: int) -> dict[str, Any]:
    profile = get_or_404(connection, "profiles", profile_id)
    counts = connection.execute(
        """
        SELECT count(DISTINCT assigned_role.id) AS role_count,
               count(DISTINCT assignment.user_id) FILTER (
                 WHERE assignment.valid_from<=CURRENT_TIMESTAMP
                   AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
               ) AS user_count
        FROM roles assigned_role
        LEFT JOIN user_role_assignments assignment ON assignment.role_id=assigned_role.id
        WHERE assigned_role.profile_id=%s
        """, (profile_id,),
    ).fetchone()
    return {"profile": profile, **counts}


def _privilege_ids(connection: Connection, profile_id: int) -> list[int]:
    return [row["privilege_id"] for row in connection.execute(
        "SELECT privilege_id FROM profile_privileges WHERE profile_id=%s ORDER BY privilege_id",
        (profile_id,),
    ).fetchall()]


def _validate_dependencies(connection: Connection, privilege_ids: set[int]) -> None:
    if not privilege_ids:
        return
    missing = connection.execute(
        """
        SELECT dependent.code AS privilege_code, required.code AS required_code
        FROM privilege_dependencies dependency
        JOIN privileges dependent ON dependent.id=dependency.privilege_id
        JOIN privileges required ON required.id=dependency.required_privilege_id
        WHERE dependency.privilege_id=ANY(%s)
          AND NOT dependency.required_privilege_id=ANY(%s)
        ORDER BY dependent.code,required.code
        """, (list(privilege_ids), list(privilege_ids)),
    ).fetchall()
    if missing:
        raise HTTPException(status_code=422, detail={
            "code": "privilege_dependency_violation", "missing": missing,
        })


def _effective_people_for_privilege(connection: Connection, code: str) -> int:
    return connection.execute(
        """
        SELECT count(DISTINCT user_account.id) AS count
        FROM users user_account
        JOIN user_role_assignments assignment ON assignment.user_id=user_account.id
        JOIN roles assigned_role ON assigned_role.id=assignment.role_id
        JOIN profile_privileges membership ON membership.profile_id=assigned_role.profile_id
        JOIN privileges privilege ON privilege.id=membership.privilege_id
        WHERE privilege.code=%s AND user_account.account_type='person'
          AND user_account.status='active'
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assigned_role.id)
        """, (code,),
    ).fetchone()["count"]


def _universal_custodian_count(connection: Connection) -> int:
    return connection.execute(
        """
        SELECT count(DISTINCT user_account.id) AS count
        FROM users user_account
        JOIN user_role_assignments assignment ON assignment.user_id=user_account.id
        JOIN roles assigned_role ON assigned_role.id=assignment.role_id
        JOIN security_levels level ON level.id=assigned_role.security_level_id
        WHERE assigned_role.is_information_governance
          AND level.level_number=(SELECT max(level_number) FROM security_levels)
          AND user_account.account_type='person' AND user_account.status='active'
          AND role_effectively_active(assigned_role.id)
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND (
            SELECT count(DISTINCT privilege.code)
            FROM profile_privileges membership
            JOIN privileges privilege ON privilege.id=membership.privilege_id
            WHERE membership.profile_id=assigned_role.profile_id
              AND privilege.code=ANY(%s)
          )=%s
        """,
        (list(CUSTODY_PRIVILEGE_CODES), len(CUSTODY_PRIVILEGE_CODES)),
    ).fetchone()["count"]


def assert_continuity(connection: Connection, before_admins: int, before_custodians: int) -> None:
    if before_admins > 0 and _effective_people_for_privilege(connection, "authorization.administer") == 0:
        raise HTTPException(status_code=409, detail="last_authorization_administrator")
    protected = connection.execute("SELECT EXISTS(SELECT 1 FROM aggregations UNION ALL SELECT 1 FROM records) AS value").fetchone()["value"]
    if protected and before_custodians > 0 and _universal_custodian_count(connection) == 0:
        raise HTTPException(status_code=409, detail="last_governance_custodian")


@router.get("/privileges", response_model=list[PrivilegeRead])
def list_privileges(limit: int=Query(500,ge=1,le=500), offset: int=Query(0,ge=0), connection: Connection=Depends(get_connection,scope="function")):
    return list(connection.execute(
        "SELECT * FROM privileges ORDER BY category,code LIMIT %s OFFSET %s", (limit,offset)
    ).fetchall())


@router.get("/privileges/{privilege_id}", response_model=PrivilegeRead)
def get_privilege(privilege_id: int, connection: Connection=Depends(get_connection,scope="function")):
    return get_or_404(connection,"privileges",privilege_id)


@router.post("/profiles", response_model=ProfileRead, status_code=201)
def create_profile(payload: ProfileCreate, connection: Connection=Depends(get_connection,scope="function")):
    return create_row(connection,"profiles",{**payload.model_dump(),"is_system":False})


@router.get("/profiles", response_model=list[ProfileRead])
def list_profiles(limit: int=Query(500,ge=1,le=500), offset: int=Query(0,ge=0), connection: Connection=Depends(get_connection,scope="function")):
    return list(connection.execute("SELECT * FROM profiles ORDER BY name,id LIMIT %s OFFSET %s",(limit,offset)).fetchall())


@router.get("/profiles/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: int, connection: Connection=Depends(get_connection,scope="function")):
    return get_or_404(connection,"profiles",profile_id)


@router.patch("/profiles/{profile_id}", response_model=ProfileRead)
def update_profile(profile_id:int,payload:ProfileUpdate,request:Request,version:int=Depends(expected_version),connection:Connection=Depends(get_connection,scope="function")):
    _reason(request)
    return update_row(connection,"profiles",profile_id,payload.model_dump(exclude_unset=True),version)


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id:int,request:Request,version:int=Depends(expected_version),connection:Connection=Depends(get_connection,scope="function")):
    profile=get_or_404(connection,"profiles",profile_id)
    _reason(request)
    if profile["is_system"]:
        raise HTTPException(status_code=409,detail="built-in profiles cannot be deleted")
    if connection.execute("SELECT EXISTS(SELECT 1 FROM roles WHERE profile_id=%s) AS value",(profile_id,)).fetchone()["value"]:
        raise HTTPException(status_code=409,detail="profile is assigned to roles")
    delete_row(connection,"profiles",profile_id,version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profiles/{profile_id}/impact")
def profile_impact(profile_id:int,connection:Connection=Depends(get_connection,scope="function")):
    return _impact(connection,profile_id)


@router.get("/profiles/{profile_id}/privileges", response_model=list[PrivilegeRead])
def profile_privileges(profile_id:int,connection:Connection=Depends(get_connection,scope="function")):
    get_or_404(connection,"profiles",profile_id)
    return list(connection.execute(
        "SELECT privilege.* FROM privileges privilege JOIN profile_privileges membership ON membership.privilege_id=privilege.id WHERE membership.profile_id=%s ORDER BY privilege.category,privilege.code",
        (profile_id,),
    ).fetchall())


@router.put("/profiles/{profile_id}/privileges")
def replace_profile_privileges(profile_id:int,payload:ProfilePrivilegeReplace,request:Request,version:int=Depends(expected_version),connection:Connection=Depends(get_connection,scope="function")):
    acquire_continuity_lock(connection)
    profile = connection.execute(
        "SELECT * FROM profiles WHERE id=%s FOR UPDATE", (profile_id,)
    ).fetchone()
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    reason=_reason(request)
    if profile["version"] != version:
        raise HTTPException(status_code=412,detail="entity has changed")
    selected=set(payload.privilege_ids)
    existing_ids={row["id"] for row in connection.execute("SELECT id FROM privileges WHERE id=ANY(%s)",(list(selected),)).fetchall()} if selected else set()
    if selected != existing_ids:
        raise HTTPException(status_code=422,detail="unknown privilege")
    _validate_dependencies(connection,selected)
    before_admins=_effective_people_for_privilege(connection,"authorization.administer")
    before_custodians=_universal_custodian_count(connection)
    old=set(_privilege_ids(connection,profile_id))
    connection.execute("DELETE FROM profile_privileges WHERE profile_id=%s AND NOT privilege_id=ANY(%s)",(profile_id,list(selected) or [0]))
    for privilege_id in selected-old:
        connection.execute("INSERT INTO profile_privileges(profile_id,privilege_id) VALUES (%s,%s)",(profile_id,privilege_id))
    assert_continuity(connection,before_admins,before_custodians)
    updated=connection.execute("UPDATE profiles SET version=version+1,date_updated=CURRENT_TIMESTAMP WHERE id=%s AND version=%s RETURNING *",(profile_id,version)).fetchone()
    connection.execute("SELECT append_domain_event('profile',%s,'PROFILE_PRIVILEGES_REPLACED',%s::jsonb,%s)",(profile_id,json.dumps({"added":sorted(selected-old),"removed":sorted(old-selected),**_impact(connection,profile_id)} ,default=str),reason))
    return {"profile":updated,"privileges":profile_privileges(profile_id,connection)}


@router.get("/roles/{role_id}/profile/impact")
def role_profile_impact(role_id:int,profile_id:int,connection:Connection=Depends(get_connection,scope="function")):
    role=get_or_404(connection,"roles",role_id); profile=get_or_404(connection,"profiles",profile_id)
    return {"role":role,"current_profile":get_or_404(connection,"profiles",role["profile_id"]),"proposed_profile":profile,
            "assigned_user_count":connection.execute("SELECT count(DISTINCT user_id) AS count FROM user_role_assignments WHERE role_id=%s",(role_id,)).fetchone()["count"]}


@router.put("/roles/{role_id}/profile", response_model=RoleRead)
def assign_role_profile(role_id:int,payload:RoleProfileAssignment,request:Request,version:int=Depends(expected_version),connection:Connection=Depends(get_connection,scope="function")):
    acquire_continuity_lock(connection)
    role=get_or_404(connection,"roles",role_id); get_or_404(connection,"profiles",payload.profile_id)
    reason=_reason(request); before_admins=_effective_people_for_privilege(connection,"authorization.administer"); before_custodians=_universal_custodian_count(connection)
    updated=update_row(connection,"roles",role_id,{"profile_id":payload.profile_id},version)
    assert_continuity(connection,before_admins,before_custodians)
    connection.execute("SELECT append_domain_event('role',%s,'PROFILE_ASSIGNED',%s::jsonb,%s)",(role_id,json.dumps({"old_profile_id":role["profile_id"],"new_profile_id":payload.profile_id}),reason))
    return updated
