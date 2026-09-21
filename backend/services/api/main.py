from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
import json
import secrets
from urllib.parse import quote
from uuid import UUID, uuid4

import psycopg
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg import Connection
from psycopg_pool import PoolTimeout
from psycopg.types.json import Jsonb

from .audit_context import (
    actor_email_context,
    actor_name_context,
    actor_user_id_context,
    actor_type_context,
    change_reason_context,
    correlation_id_context,
    event_source_context,
    request_id_context,
)
from .authentication import CSRF_COOKIE, SESSION_COOKIE, hash_secret, resolve_principal, router as authentication_router
from .crud import create_row, delete_row, get_or_404, list_rows, update_row
from .concurrency import expected_version
from .continuity_lock import acquire_continuity_shared_lock
from .config import integer_environment
from .content_storage import configured_storage, inspect_upload
from .database import close_pool, get_connection, open_pool, pool
from .document_conversion import ConversionUnavailable, UnsupportedPreview, pdf_rendition
from .schemas import (
    AggregationCreate,
    AggregationRead,
    AggregationUpdate,
    DigitalComponentCreate,
    DigitalComponentRead,
    DigitalComponentUpdate,
    ComponentReorderRequest,
    EventHistoryRead,
    RecordCreate,
    RecordDraftComponentRead,
    RecordDraftCreate,
    RecordDraftRead,
    RecordDraftUpdate,
    RecordRead,
    RecordPlacementCorrection,
    RecordUpdate,
    SearchRequest,
    SearchResponse,
    ResourceCapabilitiesRead,
    OwnershipDashboardCount,
    CreationRoleOption,
)
from .search import search_rows
from .security_level_events import append_security_level_event, validate_security_level_change
from .resource_authorization import (
    audit_governance_view_if_used, lock_visible_resource, operation_allowed, require_clearance_for_level,
    require_closed_placement_correction, require_component_operation,
    require_destination_record_permission, require_draft_owner, require_global,
    require_resource_operation,
)
from .user_management import router as user_management_router
from .classification_management import router as classification_management_router
from .browse import router as browse_router
from .favourites import router as favourites_router
from .security_levels import router as security_levels_router
from .authorization_admin import router as authorization_admin_router
from .resource_acls import router as resource_acl_router
from .governance_authorization import router as governance_authorization_router
from .security_operations import router as security_operations_router
from .authorization_policy import load_policy_context, require_audit_view


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="ERMS API",
    version="0.1.0",
    description="REST API for the Electronic Records Management System.",
    lifespan=lifespan,
)
app.include_router(user_management_router)
app.include_router(authentication_router)
app.include_router(classification_management_router)
app.include_router(browse_router)
app.include_router(favourites_router)
app.include_router(security_levels_router)
app.include_router(authorization_admin_router)
app.include_router(resource_acl_router)
app.include_router(governance_authorization_router)
app.include_router(security_operations_router)

EVENT_SOURCES = {
    "api", "web_ui", "bulk_import", "background_worker", "scheduled_job",
    "integration", "migration", "seeding", "administrative_tool", "cli", "oidc_sync",
    "directory_sync",
}


def _request_uuid(value: str | None, header_name: str) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(value))
    except ValueError as exception:
        raise ValueError(f"{header_name} must be a valid UUID") from exception


@app.middleware("http")
async def audit_request_context(request: Request, call_next):
    try:
        request_id = _request_uuid(request.headers.get("X-Request-ID"), "X-Request-ID")
        correlation_header = request.headers.get("X-Correlation-ID")
        correlation_id = (
            _request_uuid(correlation_header, "X-Correlation-ID")
            if correlation_header
            else request_id
        )
    except ValueError as exception:
        return JSONResponse(status_code=400, content={"detail": str(exception)})

    change_reason = request.headers.get("X-Change-Reason", "")
    if len(change_reason) > 2000:
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Change-Reason cannot exceed 2000 characters"},
        )

    event_source = request.headers.get("X-Event-Source", "api").strip().lower()
    if event_source not in EVENT_SOURCES:
        return JSONResponse(
            status_code=400,
            content={"detail": "X-Event-Source is not an approved event source"},
        )

    request_token = request_id_context.set(request_id)
    correlation_token = correlation_id_context.set(correlation_id)
    principal = None
    cookie_token = request.cookies.get(SESSION_COOKIE)
    authorization = request.headers.get("authorization", "")
    bearer_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else None
    session_token = bearer_token or cookie_token
    if session_token:
        try:
            with pool.connection() as authentication_connection:
                principal = resolve_principal(authentication_connection, session_token)
                request.state.policy_context = (
                    load_policy_context(authentication_connection, principal)
                    if principal else None
                )
        except PoolTimeout:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "database connection pool is busy; retry shortly"},
                headers={"Retry-After": "1", "X-Request-ID": request_id,
                         "X-Correlation-ID": correlation_id},
            )
    public_path = (
        request.url.path == "/health"
        or request.url.path == "/api/v1/auth/login"
        or request.url.path in {"/docs", "/openapi.json", "/redoc"}
    )
    if request.url.path.startswith("/api/v1/") and not public_path and principal is None:
        return JSONResponse(status_code=401, content={"detail": "authentication required"})
    if principal and principal.must_change_password and request.url.path not in {
        "/api/v1/auth/me", "/api/v1/auth/change-password", "/api/v1/auth/logout"
    }:
        return JSONResponse(status_code=403, content={"detail": "password change required"})
    if principal and cookie_token and not bearer_token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not secrets.compare_digest(hash_secret(csrf), hash_secret(request.cookies.get(CSRF_COOKIE, ""))):
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
    request.state.principal = principal
    if not hasattr(request.state, "policy_context"):
        request.state.policy_context = None
    actor_token = actor_type_context.set("user" if principal else "anonymous")
    actor_user_token = actor_user_id_context.set(str(principal.user_id) if principal else "")
    actor_name_token = actor_name_context.set(principal.name if principal else "")
    actor_email_token = actor_email_context.set(principal.email if principal else "")
    source_token = event_source_context.set(event_source)
    reason_token = change_reason_context.set(change_reason)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        change_reason_context.reset(reason_token)
        event_source_context.reset(source_token)
        actor_email_context.reset(actor_email_token)
        actor_name_context.reset(actor_name_token)
        actor_user_id_context.reset(actor_user_token)
        actor_type_context.reset(actor_token)
        correlation_id_context.reset(correlation_token)
        request_id_context.reset(request_token)


@app.exception_handler(psycopg.Error)
async def database_error_handler(_, exception: psycopg.Error):
    sqlstate = exception.sqlstate
    constraint_messages = {
        "aggregations_dates_in_order": (
            "aggregation_dates_out_of_order",
            "The aggregation's closing date cannot be earlier than its opening date.",
        ),
        "org_units_dates_in_order": (
            "organization_unit_dates_out_of_order",
            "The organization unit's deactivation date cannot be earlier than its creation date.",
        ),
        "users_dates_in_order": (
            "user_dates_out_of_order",
            "The account's deactivation date cannot be earlier than its creation date.",
        ),
        "roles_dates_in_order": (
            "role_dates_out_of_order",
            "The role's deactivation date cannot be earlier than its creation date.",
        ),
        "user_role_assignments_dates_in_order": (
            "assignment_dates_out_of_order",
            "The assignment's end date cannot be earlier than its start date.",
        ),
        "classification_schemes_dates_in_order": (
            "classification_scheme_dates_out_of_order",
            "The classification scheme's dates are not in a valid chronological order.",
        ),
        "classifications_dates_in_order": (
            "classification_dates_out_of_order",
            "The classification's deactivation date cannot be earlier than its creation date.",
        ),
    }
    constraint_name = exception.diag.constraint_name
    friendly_constraint = constraint_messages.get(constraint_name or "")
    if isinstance(exception, PoolTimeout):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        detail = "database connection pool is busy; retry shortly"
    elif sqlstate in {"23503", "23505", "P0001"}:
        status_code = status.HTTP_409_CONFLICT
        primary = exception.diag.message_primary or "database constraint violated"
        detail = (
            {
                "code": "security_hierarchy_violation",
                "message": "The security level conflicts with the containing aggregation",
                "context": exception.diag.message_detail,
            }
            if primary == "security_hierarchy_violation"
            else primary
        )
    elif friendly_constraint:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        code, message = friendly_constraint
        detail = {
            "code": code,
            "message": message,
            "technical_detail": exception.diag.message_primary
            or f"database constraint {constraint_name} was violated",
            "constraint": constraint_name,
        }
    elif isinstance(exception, (psycopg.IntegrityError, psycopg.DataError)):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        detail = exception.diag.message_primary or "database constraint violated"
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "database operation failed"
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


@app.get("/health", tags=["system"])
def health(connection: Connection = Depends(get_connection, scope="function")) -> dict[str, str]:
    connection.execute("SELECT 1")
    return {"status": "ok"}


def _creation_role_options(
    connection: Connection, parent_aggregation_id: int | None = None,
) -> list[dict]:
    parameters: list[int] = []
    owner_clause = ""
    if parent_aggregation_id is not None:
        parent = connection.execute(
            "SELECT owning_org_unit_id FROM aggregations WHERE id=%s",
            (parent_aggregation_id,),
        ).fetchone()
        if parent is None:
            raise HTTPException(status_code=409, detail="referenced aggregation does not exist")
        owner_clause = " AND role.org_unit_id=%s"
        parameters.append(parent["owning_org_unit_id"])
    rows = connection.execute(
        """SELECT DISTINCT role.id AS role_id,role.code AS role_code,
                  role.name AS role_name,unit.id AS org_unit_id,
                  unit.code AS org_unit_code,unit.name AS org_unit_name
             FROM user_role_assignments assignment
             JOIN roles role ON role.id=assignment.role_id
             JOIN org_units unit ON unit.id=role.org_unit_id
            WHERE assignment.user_id=current_user_id()
              AND CURRENT_TIMESTAMP>=assignment.valid_from
              AND (assignment.valid_until IS NULL OR CURRENT_TIMESTAMP<assignment.valid_until)
              AND role_effectively_active(role.id)""" + owner_clause +
        " ORDER BY org_unit_name,role_name,role_id",
        parameters,
    ).fetchall()
    return [{**row, "label": f"{row['org_unit_name']} — {row['role_name']}"} for row in rows]


def _select_creator_role(
    connection: Connection, requested_role_id: int | None,
    parent_aggregation_id: int | None = None,
) -> dict:
    options = _creation_role_options(connection, parent_aggregation_id)
    if not options:
        raise HTTPException(status_code=403, detail={
            "code": "creator_acl_role_not_eligible",
            "message": "You do not have a current role in the owning organizational unit.",
        })
    if requested_role_id is None:
        if len(options) != 1:
            raise HTTPException(status_code=422, detail={
                "code": "creator_acl_role_selection_required",
                "message": "Select the organizational role to create this resource for.",
            })
        return options[0]
    selected = next((row for row in options if row["role_id"] == requested_role_id), None)
    if selected is None:
        raise HTTPException(status_code=403, detail={
            "code": "creator_acl_role_not_eligible",
            "message": "The selected role is not currently eligible for this owner.",
        })
    return selected


@app.get(
    "/api/v1/creation-role-options",
    response_model=list[CreationRoleOption], tags=["authorization"],
)
def creation_role_options(
    parent_aggregation_id: int | None = None,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return _creation_role_options(connection, parent_aggregation_id)


@app.get(
    "/api/v1/dashboard/ownership-counts",
    response_model=list[OwnershipDashboardCount],
    tags=["dashboard"],
)
def dashboard_ownership_counts(
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list(connection.execute(
        """WITH eligible_units AS (
               SELECT DISTINCT unit.id,unit.code,unit.name
               FROM user_role_assignments assignment
               JOIN roles role ON role.id=assignment.role_id
               JOIN org_units unit ON unit.id=role.org_unit_id
               WHERE assignment.user_id=current_user_id()
                 AND CURRENT_TIMESTAMP>=assignment.valid_from
                 AND (assignment.valid_until IS NULL OR CURRENT_TIMESTAMP<=assignment.valid_until)
                 AND role_effectively_active(role.id)
           )
           SELECT unit.id AS org_unit_id,unit.code AS org_unit_code,
                  unit.name AS org_unit_name,
                  (SELECT count(*) FROM aggregations aggregation
                    WHERE aggregation.owning_org_unit_id=unit.id
                      AND current_user_can_view_aggregation(aggregation.id)) AS aggregation_count,
                  (SELECT count(*) FROM records record
                    WHERE record.owning_org_unit_id=unit.id
                      AND current_user_can_view_record(record.id)) AS record_count
           FROM eligible_units unit
           ORDER BY unit.name COLLATE "C",unit.id"""
    ).fetchall())


@app.post(
    "/api/v1/aggregations",
    response_model=AggregationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["aggregations"],
)
def create_aggregation(
    payload: AggregationCreate,
    connection: Connection = Depends(get_connection, scope="function"),
):
    acquire_continuity_shared_lock(connection)
    values = payload.model_dump(exclude={"creator_acl_role_id"})
    selected_role = _select_creator_role(
        connection, payload.creator_acl_role_id, payload.parent_aggregation_id,
    )
    if payload.parent_aggregation_id is None:
        level_id = payload.security_level_id or connection.execute(
            "SELECT lowest_security_level_id() AS id"
        ).fetchone()["id"]
        require_global(connection, "aggregation.create_root")
        require_clearance_for_level(connection, level_id)
        values["owning_org_unit_id"] = selected_role["org_unit_id"]
    else:
        parent = require_resource_operation(
            connection, "aggregation", payload.parent_aggregation_id,
            "aggregation.create_child", "aggregation.add_child",
        )
        level_id = payload.security_level_id or parent["security_level_id"]
        require_clearance_for_level(connection, level_id)
    connection.execute(
        "SELECT set_config('app.creator_acl_role_id',%s,true),set_config('app.event_metadata',%s,true)",
        (str(selected_role["role_id"]), json.dumps({
            "creator_acl_role_id": selected_role["role_id"],
            "creator_acl_role_code": selected_role["role_code"],
            "creator_org_unit_id": selected_role["org_unit_id"],
        })),
    )
    return create_row(connection, "aggregations", values)


@app.get("/api/v1/aggregations", response_model=list[AggregationRead], tags=["aggregations"])
def list_aggregations(
    parent_aggregation_id: int | None = None,
    owning_org_unit_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if parent_aggregation_id is not None and connection.execute(
        "SELECT 1 FROM aggregations WHERE id=%s AND current_user_can_view_aggregation(id)",
        (parent_aggregation_id,),
    ).fetchone() is None:
        return []
    return list_rows(
        connection,
        "aggregations",
        limit=limit,
        offset=offset,
        filters={"parent_aggregation_id": parent_aggregation_id,
                 "owning_org_unit_id": owning_org_unit_id},
    )


@app.post(
    "/api/v1/aggregations/search",
    response_model=SearchResponse[AggregationRead],
    tags=["aggregations"],
)
def search_aggregations(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return search_rows(connection, "aggregations", payload)


@app.get("/api/v1/aggregations/{aggregation_id}", response_model=AggregationRead, tags=["aggregations"])
def get_aggregation(aggregation_id: int, connection: Connection = Depends(get_connection, scope="function")):
    aggregation = get_or_404(connection, "aggregations", aggregation_id)
    audit_governance_view_if_used(connection, "aggregation", aggregation)
    return aggregation


@app.get("/api/v1/aggregations/{aggregation_id}/capabilities", response_model=ResourceCapabilitiesRead, tags=["authorization"])
def get_aggregation_capabilities(
    aggregation_id: int,
    connection: Connection = Depends(get_connection, scope="function"),
):
    resource = get_or_404(connection, "aggregations", aggregation_id)
    mappings = {
        "modify_metadata": ("aggregation.modify", "aggregation.modify_metadata"),
        "delete": ("aggregation.delete", "aggregation.delete"),
        "close": ("aggregation.close", "aggregation.close"),
        "reopen": ("aggregation.reopen", "aggregation.reopen"),
        "move": ("aggregation.move", "aggregation.move"),
        "reclassify": ("aggregation.reclassify", "aggregation.reclassify"),
        "change_security_level": ("aggregation.security_level.change", "aggregation.security_level.change"),
        "manage_acl": ("aggregation.acl.manage", "aggregation.acl.manage"),
        "add_child": ("aggregation.create_child", "aggregation.add_child"),
        "add_record": ("record.create", "aggregation.add_record"),
    }
    capabilities = {name: operation_allowed(connection, "aggregation", aggregation_id, *policy)
                    for name, policy in mappings.items()}
    capabilities["view"] = True
    capabilities["close"] = capabilities["close"] and resource["date_closed"] is None
    capabilities["reopen"] = capabilities["reopen"] and resource["date_closed"] is not None
    capabilities["correct_ownership"] = bool(
        resource["parent_aggregation_id"] is None
        and connection.execute(
            """SELECT user_has_global_privilege(current_user_id(),'organization.ownership.correct')
                      AND EXISTS (
                        SELECT 1 FROM user_role_assignments assignment
                        JOIN roles role ON role.id=assignment.role_id
                        JOIN security_levels role_level ON role_level.id=role.security_level_id
                        JOIN security_levels resource_level ON resource_level.id=%s
                        WHERE assignment.user_id=current_user_id() AND role.is_information_governance
                          AND assignment.valid_from<=CURRENT_TIMESTAMP
                          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
                          AND role_effectively_active(role.id)
                          AND role_level.level_number>=resource_level.level_number) AS allowed""",
            (resource["security_level_id"],),
        ).fetchone()["allowed"]
    )
    return {"resource_type": "aggregation", "resource_id": aggregation_id,
            "capabilities": capabilities}


@app.patch("/api/v1/aggregations/{aggregation_id}", response_model=AggregationRead, tags=["aggregations"])
def update_aggregation(
    aggregation_id: int,
    payload: AggregationUpdate,
    request: Request,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    existing = lock_visible_resource(connection, "aggregation", aggregation_id)
    fields = payload.model_fields_set
    metadata_fields = {"aggregation_number", "title", "description", "date_opened"}
    if fields & metadata_fields:
        require_resource_operation(
            connection, "aggregation", aggregation_id,
            "aggregation.modify", "aggregation.modify_metadata",
        )
    if "parent_aggregation_id" in fields and payload.parent_aggregation_id != existing["parent_aggregation_id"]:
        require_resource_operation(connection, "aggregation", aggregation_id, "aggregation.move", "aggregation.move")
        if payload.parent_aggregation_id is None:
            require_global(connection, "aggregation.create_root")
        else:
            destination = require_resource_operation(connection, "aggregation", payload.parent_aggregation_id,
                                       "aggregation.move", "aggregation.receive_child")
            if destination["owning_org_unit_id"] != existing["owning_org_unit_id"]:
                raise HTTPException(status_code=422, detail={
                    "code": "ownership_change_requires_confirmation",
                    "message": "Use the move command and confirm the organizational ownership change.",
                })
    if "classification_id" in fields and payload.classification_id != existing["classification_id"]:
        require_resource_operation(connection, "aggregation", aggregation_id,
                                   "aggregation.reclassify", "aggregation.reclassify")
    if "date_closed" in fields and payload.date_closed != existing["date_closed"]:
        privilege = "aggregation.close" if payload.date_closed is not None else "aggregation.reopen"
        require_resource_operation(connection, "aggregation", aggregation_id, privilege, privilege)
        if (
            payload.date_closed is not None
            and existing["date_closed"] is None
            and payload.date_closed < existing["date_opened"]
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "closure_before_opening",
                    "message": (
                        "This aggregation cannot be closed before its opening date. "
                        "Choose a closing date that is the same as or later than the opening date."
                    ),
                    "date_opened": existing["date_opened"].isoformat(),
                    "requested_date_closed": payload.date_closed.isoformat(),
                },
            )
    if "security_level_id" in fields and payload.security_level_id != existing["security_level_id"]:
        require_resource_operation(connection, "aggregation", aggregation_id,
                                   "aggregation.security_level.change", "aggregation.security_level.change")
        require_clearance_for_level(connection, payload.security_level_id)
    new_level_id = payload.security_level_id if "security_level_id" in payload.model_fields_set else None
    reason, old_number, new_number = validate_security_level_change(
        connection, request, existing["security_level_id"], new_level_id
    )
    if new_level_id is not None and new_number < old_number:
        require_global(connection, "security.resource.downgrade")
    updated = update_row(
        connection, "aggregations", aggregation_id, payload.model_dump(exclude_unset=True), version
    )
    append_security_level_event(
        connection, entity_type="aggregation", entity_id=aggregation_id,
        old_security_level_id=existing["security_level_id"], new_security_level_id=new_level_id,
        old_level_number=old_number, new_level_number=new_number, reason=reason,
    )
    return updated


@app.delete("/api/v1/aggregations/{aggregation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["aggregations"])
def delete_aggregation(aggregation_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    require_resource_operation(connection, "aggregation", aggregation_id,
                               "aggregation.delete", "aggregation.delete")
    delete_row(connection, "aggregations", aggregation_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/records", response_model=RecordRead, status_code=status.HTTP_201_CREATED, tags=["records"])
def create_record(payload: RecordCreate, connection: Connection = Depends(get_connection, scope="function")):
    acquire_continuity_shared_lock(connection)
    if connection.execute(
        "SELECT 1 FROM aggregations WHERE id=%s", (payload.aggregation_id,),
    ).fetchone() is None:
        raise HTTPException(status_code=409, detail="referenced aggregation does not exist")
    require_resource_operation(connection, "aggregation", payload.aggregation_id,
                               "record.create", "aggregation.add_record")
    selected_role = _select_creator_role(
        connection, payload.creator_acl_role_id, payload.aggregation_id,
    )
    level_id = payload.security_level_id or connection.execute(
        "SELECT lowest_security_level_id() AS id"
    ).fetchone()["id"]
    require_clearance_for_level(connection, level_id)
    connection.execute(
        "SELECT set_config('app.creator_acl_role_id',%s,true),set_config('app.event_metadata',%s,true)",
        (str(selected_role["role_id"]), json.dumps({
            "creator_acl_role_id": selected_role["role_id"],
            "creator_acl_role_code": selected_role["role_code"],
            "creator_org_unit_id": selected_role["org_unit_id"],
        })),
    )
    return create_row(
        connection, "records", payload.model_dump(exclude={"creator_acl_role_id"}),
    )


@app.get("/api/v1/records", response_model=list[RecordRead], tags=["records"])
def list_records(
    aggregation_id: int | None = None,
    owning_org_unit_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    if aggregation_id is not None and connection.execute(
        "SELECT 1 FROM aggregations WHERE id=%s AND current_user_can_view_aggregation(id)",
        (aggregation_id,),
    ).fetchone() is None:
        return []
    return list_rows(
        connection,
        "records",
        limit=limit,
        offset=offset,
        filters={"aggregation_id": aggregation_id,
                 "owning_org_unit_id": owning_org_unit_id},
    )


@app.post(
    "/api/v1/records/search",
    response_model=SearchResponse[RecordRead],
    tags=["records"],
)
def search_records(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return search_rows(connection, "records", payload)


@app.get("/api/v1/records/{record_id}", response_model=RecordRead, tags=["records"])
def get_record(record_id: int, connection: Connection = Depends(get_connection, scope="function")):
    record = get_or_404(connection, "records", record_id)
    audit_governance_view_if_used(connection, "record", record)
    return record


@app.get("/api/v1/records/{record_id}/capabilities", response_model=ResourceCapabilitiesRead, tags=["authorization"])
def get_record_capabilities(
    record_id: int,
    connection: Connection = Depends(get_connection, scope="function"),
):
    get_or_404(connection, "records", record_id)
    component_metadata = connection.execute(
        "SELECT current_user_can_list_record_components(%s) AS allowed", (record_id,),
    ).fetchone()["allowed"]
    mappings = {
        "modify_metadata": ("record.modify", "record.modify_metadata"),
        "delete": ("record.delete", "record.delete"),
        "move": ("record.move", "record.move"),
        "change_security_level": ("record.security_level.change", "record.security_level.change"),
        "manage_acl": ("record.acl.manage", "record.acl.manage"),
        "view_component": ("record.component.view", "record.component.view"),
        "download_component": ("record.component.download", "record.component.download"),
        "add_component": ("record.component.add", "record.component.add"),
        "replace_component": ("record.component.replace", "record.component.replace"),
        "remove_component": ("record.component.remove", "record.component.remove"),
        "reorder_components": ("record.component.reorder", "record.component.reorder"),
    }
    capabilities = {name: operation_allowed(connection, "record", record_id, *policy)
                    for name, policy in mappings.items()}
    capabilities.update({"view": True, "list_components": component_metadata,
                         "share_component": False, "print_component": False})
    return {"resource_type": "record", "resource_id": record_id,
            "capabilities": capabilities}


@app.patch("/api/v1/records/{record_id}", response_model=RecordRead, tags=["records"])
def update_record(
    record_id: int,
    payload: RecordUpdate,
    request: Request,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    existing = lock_visible_resource(connection, "record", record_id)
    fields = payload.model_fields_set
    metadata_fields = {"record_number", "title", "description", "date_originated"}
    if fields & metadata_fields:
        require_resource_operation(
            connection, "record", record_id, "record.modify", "record.modify_metadata",
        )
    if "aggregation_id" in fields and payload.aggregation_id != existing["aggregation_id"]:
        require_resource_operation(connection, "record", record_id, "record.move", "record.move")
        destination = require_resource_operation(connection, "aggregation", payload.aggregation_id,
                                   "record.move", "aggregation.receive_record")
        if destination["owning_org_unit_id"] != existing["owning_org_unit_id"]:
            raise HTTPException(status_code=422, detail={
                "code": "ownership_change_requires_confirmation",
                "message": "Use the move command and confirm the organizational ownership change.",
            })
    if "security_level_id" in fields and payload.security_level_id != existing["security_level_id"]:
        require_resource_operation(connection, "record", record_id,
                                   "record.security_level.change", "record.security_level.change")
        require_clearance_for_level(connection, payload.security_level_id)
    new_level_id = payload.security_level_id if "security_level_id" in payload.model_fields_set else None
    reason, old_number, new_number = validate_security_level_change(
        connection, request, existing["security_level_id"], new_level_id
    )
    if new_level_id is not None and new_number < old_number:
        require_global(connection, "security.resource.downgrade")
    updated = update_row(connection, "records", record_id, payload.model_dump(exclude_unset=True), version)
    append_security_level_event(
        connection, entity_type="record", entity_id=record_id,
        old_security_level_id=existing["security_level_id"], new_security_level_id=new_level_id,
        old_level_number=old_number, new_level_number=new_number, reason=reason,
    )
    return updated


@app.delete("/api/v1/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["records"])
def delete_record(record_id: int, version: int = Depends(expected_version), connection: Connection = Depends(get_connection, scope="function")):
    require_resource_operation(connection, "record", record_id, "record.delete", "record.delete")
    delete_row(connection, "records", record_id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _effective_closure(connection: Connection, aggregation_id: int) -> dict | None:
    return connection.execute(
        """WITH RECURSIVE ancestry AS (
             SELECT id,parent_aggregation_id,date_closed,0 AS depth FROM aggregations WHERE id=%s
             UNION ALL SELECT parent.id,parent.parent_aggregation_id,parent.date_closed,child.depth+1
             FROM aggregations parent JOIN ancestry child ON child.parent_aggregation_id=parent.id)
           SELECT id,date_closed FROM ancestry WHERE date_closed IS NOT NULL ORDER BY depth LIMIT 1""",
        (aggregation_id,),
    ).fetchone()


def _governance_basis(connection: Connection, security_level_ids: list[int]) -> list[dict]:
    return list(connection.execute(
        """SELECT DISTINCT role.id,role.code,role.name,level.level_number
           FROM user_role_assignments assignment JOIN roles role ON role.id=assignment.role_id
           JOIN security_levels level ON level.id=role.security_level_id
           JOIN security_levels required ON required.id=ANY(%s)
           WHERE assignment.user_id=current_user_id() AND role.is_information_governance
             AND assignment.valid_from<=CURRENT_TIMESTAMP
             AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
             AND role_effectively_active(role.id) AND level.level_number>=required.level_number
           ORDER BY role.id""", (security_level_ids,),
    ).fetchall())


@app.post("/api/v1/records/{record_id}/correct-placement", response_model=RecordRead, tags=["records"])
def correct_record_placement(
    record_id: int, payload: RecordPlacementCorrection, request: Request,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    source = require_resource_operation(connection, "record", record_id, "record.move", "record.move")
    reason = request.headers.get("X-Change-Reason", "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="X-Change-Reason is required")
    destination = require_closed_placement_correction(
        connection, payload.destination_aggregation_id, source["security_level_id"], "record.move",
    )
    closure = _effective_closure(connection, destination["id"])
    if closure is None:
        raise HTTPException(status_code=409, detail="destination is not effectively closed; use the ordinary move operation")
    if source["aggregation_id"] == destination["id"]:
        raise HTTPException(status_code=409, detail="record is already in the destination aggregation")
    basis = _governance_basis(connection, [source["security_level_id"], destination["security_level_id"]])
    connection.execute(
        "SELECT set_config('app.closed_record_placement_correction','authorized',true), set_config('app.change_reason',%s,true)",
        (reason,),
    )
    moved = update_row(connection, "records", record_id, {"aggregation_id": destination["id"]}, version)
    connection.execute(
        "SELECT append_domain_event('record',%s,'CLOSED_AGGREGATION_RECORD_CORRECTED',%s::jsonb,%s)",
        (record_id, Jsonb({"source_aggregation_id": source["aggregation_id"],
                          "destination_aggregation_id": destination["id"],
                          "effective_closure_aggregation_id": closure["id"],
                          "effective_closure_date": closure["date_closed"].isoformat(),
                          "closure_date_unchanged": True,
                          "authorization_basis": "information_governance",
                          "governance_roles": basis}), reason),
    )
    return moved


def _open_draft(connection: Connection, draft_id: int, *, lock: bool = False) -> dict:
    # A draft, including its staged components, is the in-progress record
    # creation package. Re-evaluate record.create on every operation so a
    # privilege removed after the draft was opened takes effect immediately.
    require_global(connection, "record.create")
    require_draft_owner(connection, draft_id)
    suffix = " FOR UPDATE" if lock else ""
    draft = connection.execute(
        f"SELECT * FROM record_drafts WHERE id = %s{suffix}", (draft_id,)
    ).fetchone()
    if draft is None:
        raise HTTPException(status_code=404, detail="record draft not found")
    if draft["status"] != "open":
        raise HTTPException(status_code=409, detail="record draft is no longer open")
    if draft["expires_at"] <= datetime.now(draft["expires_at"].tzinfo):
        raise HTTPException(status_code=410, detail="record draft has expired")
    return draft


@app.post("/api/v1/record-drafts", response_model=RecordDraftRead, status_code=201, tags=["record drafts"])
def create_record_draft(payload: RecordDraftCreate, connection: Connection = Depends(get_connection, scope="function")):
    require_global(connection, "record.create")
    values = payload.model_dump(exclude_none=True)
    values["owner_user_id"] = connection.execute("SELECT current_user_id() AS id").fetchone()["id"]
    if not values:
        return connection.execute("INSERT INTO record_drafts DEFAULT VALUES RETURNING *").fetchone()
    return create_row(connection, "record_drafts", values)


@app.get("/api/v1/record-drafts/{draft_id}", response_model=RecordDraftRead, tags=["record drafts"])
def get_record_draft(draft_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return _open_draft(connection, draft_id)


@app.patch("/api/v1/record-drafts/{draft_id}", response_model=RecordDraftRead, tags=["record drafts"])
def update_record_draft(draft_id: int, payload: RecordDraftUpdate, connection: Connection = Depends(get_connection, scope="function")):
    _open_draft(connection, draft_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _open_draft(connection, draft_id)
    assignments = ", ".join(f"{key} = %s" for key in values)
    return connection.execute(
        f"UPDATE record_drafts SET {assignments} WHERE id = %s RETURNING *",
        (*values.values(), draft_id),
    ).fetchone()


@app.delete("/api/v1/record-drafts/{draft_id}", status_code=204, tags=["record drafts"])
def discard_record_draft(draft_id: int, connection: Connection = Depends(get_connection, scope="function")):
    _open_draft(connection, draft_id, lock=True)
    connection.execute("DELETE FROM record_drafts WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.get("/api/v1/record-drafts/{draft_id}/components", response_model=list[RecordDraftComponentRead], tags=["record drafts"])
def list_record_draft_components(draft_id: int, connection: Connection = Depends(get_connection, scope="function")):
    _open_draft(connection, draft_id)
    return list(connection.execute(
        """SELECT id, draft_id, component_order, file_name, date_created,
                  date_originated, mime_type, size_in_bytes, checksum_algo,
                  checksum_value, 'staged' AS content_status,
                  'temporary' AS storage_backend
           FROM record_draft_components WHERE draft_id = %s ORDER BY component_order""",
        (draft_id,),
    ).fetchall())


@app.post("/api/v1/record-drafts/{draft_id}/components", response_model=RecordDraftComponentRead, status_code=201, tags=["record drafts"])
def upload_record_draft_component(
    draft_id: int,
    file: UploadFile = File(...),
    component_order: int = Form(..., gt=0),
    date_originated: datetime | None = Form(default=None),
    connection: Connection = Depends(get_connection, scope="function"),
):
    _open_draft(connection, draft_id, lock=True)
    inspected = inspect_upload(file)
    component = connection.execute(
        """INSERT INTO record_draft_components
               (draft_id, component_order, file_name, date_originated, mime_type,
                size_in_bytes, checksum_algo, checksum_value, content_status)
           VALUES (%s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), %s, %s, 'sha256', %s, 'uploading')
           RETURNING id""",
        (draft_id, component_order, file.filename or "unnamed", date_originated,
         file.content_type or "application/octet-stream", inspected.size_in_bytes,
         inspected.checksum_value),
    ).fetchone()
    configured_storage().store_draft_upload(connection, component["id"], file)
    component = connection.execute(
        """SELECT id, draft_id, component_order, file_name, date_created,
                  date_originated, mime_type, size_in_bytes, checksum_algo,
                  checksum_value, 'staged' AS content_status,
                  'temporary' AS storage_backend
           FROM record_draft_components WHERE id = %s""",
        (component["id"],),
    ).fetchone()
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return component


def _reorder_components(connection: Connection, table: str, parent_column: str, parent_id: int, payload: ComponentReorderRequest) -> None:
    requested = {item.id: item.component_order for item in payload.components}
    if len(requested) != len(payload.components) or set(requested.values()) != set(range(1, len(requested) + 1)):
        raise HTTPException(status_code=422, detail="component order must contain each position from 1 through the component count")
    existing = {
        row["id"] for row in connection.execute(
            f"SELECT id FROM {table} WHERE {parent_column} = %s FOR UPDATE", (parent_id,)
        ).fetchall()
    }
    if existing != set(requested):
        raise HTTPException(status_code=422, detail="component list must contain every component exactly once")
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for component_id, position in requested.items():
        connection.execute(
            f"UPDATE {table} SET component_order = %s WHERE id = %s", (position, component_id)
        )


@app.put("/api/v1/record-drafts/{draft_id}/components/order", status_code=204, tags=["record drafts"])
def reorder_record_draft_components(draft_id: int, payload: ComponentReorderRequest, connection: Connection = Depends(get_connection, scope="function")):
    _open_draft(connection, draft_id, lock=True)
    _reorder_components(connection, "record_draft_components", "draft_id", draft_id, payload)
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.delete("/api/v1/record-drafts/{draft_id}/components/{component_id}", status_code=204, tags=["record drafts"])
def delete_record_draft_component(draft_id: int, component_id: int, connection: Connection = Depends(get_connection, scope="function")):
    _open_draft(connection, draft_id, lock=True)
    deleted = connection.execute(
        "DELETE FROM record_draft_components WHERE id = %s AND draft_id = %s RETURNING id",
        (component_id, draft_id),
    ).fetchone()
    if deleted is None:
        raise HTTPException(status_code=404, detail="record draft component not found")
    rows = connection.execute(
        "SELECT id FROM record_draft_components WHERE draft_id = %s ORDER BY component_order", (draft_id,)
    ).fetchall()
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for position, row in enumerate(rows, 1):
        connection.execute("UPDATE record_draft_components SET component_order = %s WHERE id = %s", (position, row["id"]))
    connection.execute("UPDATE record_drafts SET date_updated = CURRENT_TIMESTAMP WHERE id = %s", (draft_id,))
    return Response(status_code=204)


@app.post("/api/v1/record-drafts/{draft_id}/commit", response_model=RecordRead, status_code=201, tags=["record drafts"])
def commit_record_draft(
    draft_id: int, creator_acl_role_id: int | None = None,
    connection: Connection = Depends(get_connection, scope="function"),
):
    draft = _open_draft(connection, draft_id, lock=True)
    missing = [name for name in ("aggregation_id", "record_number", "title") if not draft.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"draft is missing required fields: {', '.join(missing)}")
    security_level_id = draft["security_level_id"]
    if security_level_id is None:
        security_level_id = connection.execute(
            "SELECT id FROM security_levels ORDER BY level_number,id LIMIT 1"
        ).fetchone()["id"]
    require_resource_operation(
        connection, "aggregation", draft["aggregation_id"],
        "record.create", "aggregation.add_record",
    )
    selected_role = _select_creator_role(
        connection, creator_acl_role_id, draft["aggregation_id"],
    )
    require_clearance_for_level(connection, security_level_id)
    connection.execute(
        "SELECT set_config('app.creator_acl_role_id',%s,true),set_config('app.event_metadata',%s,true)",
        (str(selected_role["role_id"]), json.dumps({
            "creator_acl_role_id": selected_role["role_id"],
            "creator_acl_role_code": selected_role["role_code"],
            "creator_org_unit_id": selected_role["org_unit_id"],
        })),
    )
    components = connection.execute(
        "SELECT * FROM record_draft_components WHERE draft_id = %s ORDER BY component_order FOR UPDATE", (draft_id,)
    ).fetchall()
    record = create_row(connection, "records", {
        "aggregation_id": draft["aggregation_id"], "record_number": draft["record_number"],
        "title": draft["title"], "description": draft["description"],
        "date_originated": draft["date_originated"],
        "security_level_id": security_level_id,
    })
    incomplete = [item["file_name"] for item in components if item["content_status"] != "available"]
    if incomplete:
        raise HTTPException(status_code=409, detail="all draft component uploads must be complete")
    for staged in components:
        component = create_row(connection, "digital_components", {
            "record_id": record["id"], "component_order": staged["component_order"],
            "file_name": staged["file_name"], "date_originated": staged["date_originated"],
            "mime_type": staged["mime_type"], "size_in_bytes": staged["size_in_bytes"],
            "checksum_algo": staged["checksum_algo"], "checksum_value": staged["checksum_value"],
            "storage_backend": "postgresql", "content_status": "available",
        })
        configured_storage().promote_draft(connection, staged["id"], component["id"])
        _append_content_event(connection, component["id"], "CONTENT_UPLOADED", {
            "file_name": component["file_name"], "mime_type": component["mime_type"],
            "size_in_bytes": component["size_in_bytes"], "checksum_algo": component["checksum_algo"],
            "checksum_value": component["checksum_value"], "record_creation": True,
        })
    connection.execute("DELETE FROM record_drafts WHERE id = %s", (draft_id,))
    return record


@app.post("/api/v1/record-drafts/{draft_id}/commit-placement-correction", response_model=RecordRead, status_code=201, tags=["record drafts"])
def commit_record_draft_placement_correction(
    draft_id: int,
    request: Request,
    creator_acl_role_id: int | None = None,
    connection: Connection = Depends(get_connection, scope="function"),
):
    draft = _open_draft(connection, draft_id, lock=True)
    if not draft.get("aggregation_id"):
        raise HTTPException(status_code=422, detail="draft destination is required")
    security_level_id = draft["security_level_id"]
    if security_level_id is None:
        security_level_id = connection.execute(
            "SELECT id FROM security_levels ORDER BY level_number,id LIMIT 1"
        ).fetchone()["id"]
    reason = request.headers.get("X-Change-Reason", "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="X-Change-Reason is required")
    destination = require_closed_placement_correction(
        connection, draft["aggregation_id"], security_level_id, "record.create",
    )
    closure = _effective_closure(connection, destination["id"])
    if closure is None:
        raise HTTPException(status_code=409, detail="destination is not effectively closed; use the ordinary commit operation")
    basis = _governance_basis(connection, [security_level_id, destination["security_level_id"]])
    connection.execute(
        "SELECT set_config('app.closed_record_placement_correction','authorized',true), set_config('app.change_reason',%s,true)",
        (reason,),
    )
    record = commit_record_draft(draft_id, creator_acl_role_id, connection)
    connection.execute(
        "SELECT append_domain_event('record',%s,'CLOSED_AGGREGATION_RECORD_CORRECTED',%s::jsonb,%s)",
        (record["id"], Jsonb({
            "source_aggregation_id": None,
            "destination_aggregation_id": destination["id"],
            "effective_closure_aggregation_id": closure["id"],
            "effective_closure_date": closure["date_closed"].isoformat(),
            "closure_date_unchanged": True,
            "authorization_basis": "information_governance",
            "governance_roles": basis,
        }), reason),
    )
    return record


@app.post(
    "/api/v1/digital-components",
    response_model=DigitalComponentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["digital components"],
)
def create_digital_component(
    payload: DigitalComponentCreate,
    connection: Connection = Depends(get_connection, scope="function"),
):
    require_resource_operation(connection, "record", payload.record_id,
                               "record.component.add", "record.component.add")
    return create_row(connection, "digital_components", payload.model_dump())


@app.get(
    "/api/v1/digital-components",
    response_model=list[DigitalComponentRead],
    tags=["digital components"],
)
def list_digital_components(
    record_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "digital_components",
        limit=limit,
        offset=offset,
        filters={"record_id": record_id},
        order_by=("record_id", "component_order"),
    )


@app.post(
    "/api/v1/digital-components/search",
    response_model=SearchResponse[DigitalComponentRead],
    tags=["digital components"],
)
def search_digital_components(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return search_rows(connection, "digital_components", payload)


@app.get(
    "/api/v1/digital-components/{component_id}",
    response_model=DigitalComponentRead,
    tags=["digital components"],
)
def get_digital_component(component_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "digital_components", component_id)


@app.patch(
    "/api/v1/digital-components/{component_id}",
    response_model=DigitalComponentRead,
    tags=["digital components"],
)
def update_digital_component(
    component_id: int,
    payload: DigitalComponentUpdate,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    component, _ = require_component_operation(
        connection, component_id, "record.component.replace", "record.component.replace")
    if "record_id" in payload.model_fields_set and payload.record_id != component["record_id"]:
        raise HTTPException(status_code=422, detail="moving digital components between records is not supported")
    return update_row(
        connection,
        "digital_components",
        component_id,
        payload.model_dump(exclude_unset=True),
        version,
    )


@app.delete(
    "/api/v1/digital-components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["digital components"],
)
def delete_digital_component(
    component_id: int,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    component, _ = require_component_operation(
        connection, component_id, "record.component.remove", "record.component.remove")
    delete_row(connection, "digital_components", component_id, version)
    remaining = connection.execute(
        "SELECT id FROM digital_components WHERE record_id = %s ORDER BY component_order",
        (component["record_id"],),
    ).fetchall()
    connection.execute("SET CONSTRAINTS ALL DEFERRED")
    for position, row in enumerate(remaining, 1):
        connection.execute(
            "UPDATE digital_components SET component_order = %s WHERE id = %s",
            (position, row["id"]),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put(
    "/api/v1/records/{record_id}/digital-components/order",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["digital components"],
)
def reorder_digital_components(
    record_id: int,
    payload: ComponentReorderRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    require_resource_operation(connection, "record", record_id,
                               "record.component.reorder", "record.component.reorder")
    _reorder_components(connection, "digital_components", "record_id", record_id, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _append_content_event(
    connection: Connection,
    component_id: int,
    operation: str,
    metadata: dict,
) -> None:
    connection.execute(
        "SELECT append_domain_event(%s, %s, %s, %s)",
        ("digital_component", component_id, operation, Jsonb(metadata)),
    )


def _content_range(value: str | None, total: int) -> tuple[int, int, int]:
    """Return an inclusive-exclusive byte interval and HTTP response status."""
    if value is None:
        return 0, total, 200
    if not value.startswith("bytes=") or "," in value:
        raise HTTPException(
            status_code=416, detail="invalid or multiple byte ranges are not supported",
            headers={"Content-Range": f"bytes */{total}"},
        )
    specification = value[6:].strip()
    try:
        first, last = specification.split("-", 1)
        if not first:
            suffix = int(last)
            if suffix <= 0 or total == 0:
                raise ValueError
            start = max(0, total - suffix)
            end = total
        else:
            start = int(first)
            end = total if not last else min(total, int(last) + 1)
            if start < 0 or start >= total or end <= start:
                raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=416, detail="requested byte range is not satisfiable",
            headers={"Content-Range": f"bytes */{total}"},
        )
    return start, end, 206


@app.post(
    "/api/v1/records/{record_id}/digital-components/upload",
    response_model=DigitalComponentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["digital component content"],
)
def upload_digital_component(
    record_id: int,
    file: UploadFile = File(...),
    component_order: int = Form(..., gt=0),
    date_originated: datetime | None = Form(default=None),
    connection: Connection = Depends(get_connection, scope="function"),
):
    require_resource_operation(connection, "record", record_id,
                               "record.component.add", "record.component.add")
    inspected = inspect_upload(file)
    mime_type = file.content_type or "application/octet-stream"
    component = create_row(
        connection,
        "digital_components",
        {
            "record_id": record_id,
            "component_order": component_order,
            "file_name": file.filename or "unnamed",
            "date_originated": date_originated,
            "mime_type": mime_type,
            "size_in_bytes": inspected.size_in_bytes,
            "checksum_algo": "sha256",
            "checksum_value": inspected.checksum_value,
            "storage_backend": "postgresql",
            "content_status": "available",
        },
    )
    uploaded = configured_storage().store_upload(connection, component["id"], file)
    component = get_or_404(connection, "digital_components", component["id"])
    _append_content_event(
        connection,
        component["id"],
        "CONTENT_UPLOADED",
        {"file_name": component["file_name"], "mime_type": mime_type,
         "size_in_bytes": uploaded.size_in_bytes, "checksum_algo": "sha256",
         "checksum_value": uploaded.checksum_value},
    )
    return component


@app.api_route(
    "/api/v1/digital-components/{component_id}/content",
    methods=["GET", "HEAD"],
    tags=["digital component content"],
)
def download_digital_component_content(
    component_id: int,
    request: Request,
    connection: Connection = Depends(get_connection, scope="function"),
):
    component, _ = require_component_operation(
        connection, component_id, "record.component.download", "record.component.download")
    storage = configured_storage()
    location = storage.location(connection, component_id)
    if location is None:
        raise HTTPException(status_code=404, detail="digital component content not found")
    _append_content_event(connection, component_id, "CONTENT_DOWNLOADED", {
        "size_in_bytes": component["size_in_bytes"],
        "checksum_algo": component["checksum_algo"],
        "checksum_value": component["checksum_value"],
    })
    encoded_name = quote(component["file_name"], safe="")
    start, end, response_status = _content_range(request.headers.get("range"), location.size_in_bytes)
    length = end - start
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "Content-Length": str(length),
        "Accept-Ranges": "bytes",
        "ETag": f'"sha256-{component["checksum_value"]}"',
    }
    if response_status == 206:
        headers["Content-Range"] = f"bytes {start}-{end - 1}/{location.size_in_bytes}"
    if request.method == "HEAD":
        return Response(status_code=response_status, media_type=component["mime_type"], headers=headers)
    return StreamingResponse(
        storage.iter_content(location, start, end),
        status_code=response_status,
        media_type=component["mime_type"],
        headers=headers,
    )


@app.api_route(
    "/api/v1/digital-components/{component_id}/rendition",
    methods=["GET", "HEAD"],
    tags=["digital component content"],
)
def view_digital_component_rendition(
    component_id: int,
    request: Request,
    connection: Connection = Depends(get_connection, scope="function"),
):
    component, _ = require_component_operation(
        connection, component_id, "record.component.view", "record.component.view")
    storage = configured_storage()
    location = storage.location(connection, component_id)
    if location is None:
        raise HTTPException(status_code=404, detail="digital component content not found")
    mime_type = component["mime_type"].lower()
    native_preview = (
        mime_type in {
            "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/avif",
        }
        or mime_type.startswith("audio/")
        or mime_type.startswith("video/")
    )
    if native_preview or mime_type == "application/pdf":
        rendered_mime = mime_type if native_preview else "application/pdf"
        _append_content_event(connection, component_id, "CONTENT_VIEWED", {
            "rendition_mime_type": rendered_mime,
            "rendering_method": "browser-native" if native_preview else "original",
            "original_checksum": component["checksum_value"],
        })
        encoded_name = quote(component["file_name"], safe="")
        start, end, response_status = _content_range(request.headers.get("range"), location.size_in_bytes)
        headers = {
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(end - start),
            "Accept-Ranges": "bytes",
            "ETag": f'"sha256-{component["checksum_value"]}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        }
        if response_status == 206:
            headers["Content-Range"] = f"bytes {start}-{end - 1}/{location.size_in_bytes}"
        if request.method == "HEAD":
            return Response(status_code=response_status, media_type=rendered_mime, headers=headers)
        return StreamingResponse(
            storage.iter_content(location, start, end), status_code=response_status,
            media_type=rendered_mime, headers=headers,
        )
    maximum_source = integer_environment("MAX_RENDITION_SIZE_BYTES", 100 * 1024 * 1024, minimum=1)
    if location.size_in_bytes > maximum_source:
        raise HTTPException(status_code=413, detail="source document exceeds the configured rendition size limit")
    content = storage.read(connection, component_id)
    if content is None:
        raise HTTPException(status_code=404, detail="digital component content not found")
    try:
        rendition, method = pdf_rendition(content, component["file_name"], mime_type)
    except UnsupportedPreview as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except ConversionUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    _append_content_event(connection, component_id, "CONTENT_VIEWED", {
        "rendition_mime_type": "application/pdf", "rendering_method": method,
        "original_checksum": component["checksum_value"],
    })
    encoded_name = quote(f"{component['file_name']}.pdf", safe="")
    return StreamingResponse(
        BytesIO(rendition),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )


@app.put(
    "/api/v1/digital-components/{component_id}/content",
    response_model=DigitalComponentRead,
    tags=["digital component content"],
)
def replace_digital_component_content(
    component_id: int,
    file: UploadFile = File(...),
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    current, _ = require_component_operation(
        connection, component_id, "record.component.replace", "record.component.replace")
    if current["version"] != version:
        return update_row(connection, "digital_components", component_id, {}, version)
    mime_type = file.content_type or "application/octet-stream"
    inspected = inspect_upload(file)
    uploaded = configured_storage().store_upload(connection, component_id, file)
    component = update_row(connection, "digital_components", component_id, {
        "file_name": file.filename or "unnamed",
        "mime_type": mime_type,
        "size_in_bytes": inspected.size_in_bytes,
        "checksum_algo": "sha256",
        "checksum_value": inspected.checksum_value,
        "storage_backend": "postgresql",
        "storage_key": None,
        "content_status": "available",
    }, version)
    _append_content_event(connection, component_id, "CONTENT_REPLACED", {
        "file_name": component["file_name"], "mime_type": mime_type,
        "size_in_bytes": uploaded.size_in_bytes, "checksum_algo": "sha256",
        "checksum_value": uploaded.checksum_value,
    })
    return component


@app.delete(
    "/api/v1/digital-components/{component_id}/content",
    response_model=DigitalComponentRead,
    tags=["digital component content"],
)
def delete_digital_component_content(
    component_id: int,
    version: int = Depends(expected_version),
    connection: Connection = Depends(get_connection, scope="function"),
):
    require_component_operation(
        connection, component_id, "record.component.remove", "record.component.remove")
    configured_storage().delete(connection, component_id)
    component = update_row(connection, "digital_components", component_id, {
        "content_status": "deleted",
    }, version)
    _append_content_event(connection, component_id, "CONTENT_DELETED", {
        "size_in_bytes": component["size_in_bytes"],
        "checksum_algo": component["checksum_algo"],
        "checksum_value": component["checksum_value"],
    })
    return component


@app.get(
    "/api/v1/event-history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def list_event_history(
    entity_type: str | None = None,
    entity_id: int | None = None,
    operation: str | None = None,
    request_id: UUID | None = None,
    correlation_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    return list_rows(
        connection,
        "event_history",
        limit=limit,
        offset=offset,
        filters={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operation": operation,
            "request_id": request_id,
            "correlation_id": correlation_id,
        },
        order_by=("occurred_at", "id"),
        descending=True,
    )


@app.post(
    "/api/v1/event-history/search",
    response_model=SearchResponse[EventHistoryRead],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def search_event_history(
    payload: SearchRequest,
    connection: Connection = Depends(get_connection, scope="function"),
):
    return search_rows(connection, "event_history", payload)


@app.get(
    "/api/v1/event-history/operations",
    response_model=list[str],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def list_event_history_operations(
    connection: Connection = Depends(get_connection, scope="function"),
):
    """Return every operation represented in the immutable audit history."""
    return _distinct_event_history_values(connection, "operation")


def _distinct_event_history_values(
    connection: Connection, column: str,
) -> list[str]:
    """Return sorted nonblank values for a trusted event-history column."""
    if column not in {"entity_type", "operation", "source", "actor_type"}:
        raise ValueError("unsupported event-history filter column")
    return [
        row[column]
        for row in connection.execute(
            f"""
            SELECT DISTINCT {column}
              FROM event_history
             WHERE {column} IS NOT NULL
               AND btrim({column}) <> ''
             ORDER BY {column}
            """
        ).fetchall()
    ]


@app.get(
    "/api/v1/event-history/filter-options",
    response_model=dict[str, list[str]],
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def list_event_history_filter_options(
    connection: Connection = Depends(get_connection, scope="function"),
):
    """Return authoritative values for every categorical audit filter."""
    return {
        "entity_types": _distinct_event_history_values(connection, "entity_type"),
        "operations": _distinct_event_history_values(connection, "operation"),
        "sources": _distinct_event_history_values(connection, "source"),
        "actor_types": _distinct_event_history_values(connection, "actor_type"),
    }


@app.get(
    "/api/v1/event-history/{event_id}",
    response_model=EventHistoryRead,
    tags=["event history"],
    dependencies=[Depends(require_audit_view)],
)
def get_event_history(event_id: int, connection: Connection = Depends(get_connection, scope="function")):
    return get_or_404(connection, "event_history", event_id)


def _entity_history(
    connection: Connection,
    entity_type: str,
    entity_id: int,
    limit: int,
    offset: int,
):
    return list_rows(
        connection,
        "event_history",
        limit=limit,
        offset=offset,
        filters={"entity_type": entity_type, "entity_id": entity_id},
        order_by=("occurred_at", "id"),
        descending=True,
    )


@app.get(
    "/api/v1/aggregations/{aggregation_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_aggregation_history(
    aggregation_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    live = connection.execute(
        "SELECT 1 FROM aggregations WHERE id=%s AND current_user_can_view_aggregation(id)",
        (aggregation_id,),
    ).fetchone()
    deleted = connection.execute(
        "SELECT 1 FROM authorized_event_history WHERE entity_type='aggregation' AND entity_id=%s "
        "AND operation='DELETE' AND user_has_global_privilege(current_user_id(),'audit.view')",
        (aggregation_id,),
    ).fetchone()
    if live is None and deleted is None:
        raise HTTPException(status_code=404, detail="aggregation not found")
    return _entity_history(connection, "aggregation", aggregation_id, limit, offset)


@app.get(
    "/api/v1/records/{record_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_record_history(
    record_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    live = connection.execute(
        "SELECT 1 FROM records WHERE id=%s AND current_user_can_view_record(id)", (record_id,),
    ).fetchone()
    deleted = connection.execute(
        "SELECT 1 FROM authorized_event_history WHERE entity_type='record' AND entity_id=%s "
        "AND operation='DELETE' AND user_has_global_privilege(current_user_id(),'audit.view')",
        (record_id,),
    ).fetchone()
    if live is None and deleted is None:
        raise HTTPException(status_code=404, detail="record not found")
    return _entity_history(connection, "record", record_id, limit, offset)


@app.get(
    "/api/v1/digital-components/{component_id}/history",
    response_model=list[EventHistoryRead],
    tags=["event history"],
)
def get_digital_component_history(
    component_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    connection: Connection = Depends(get_connection, scope="function"),
):
    get_or_404(connection, "digital_components", component_id)
    return _entity_history(connection, "digital_component", component_id, limit, offset)
