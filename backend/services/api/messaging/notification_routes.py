"""Privilege-gated configuration and controlled tests; no production send route."""

from uuid import UUID
from dataclasses import asdict
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import Field, StrictInt
from ..entity_localization import (
    preferred_language_for_user,
    localize_rows,
    localized_projection,
)
from ..audit_context import decode_change_reason
from ..authentication import Principal, principal_from_request
from ..authorization_policy import require_global_privilege
from . import notification_configuration as config
from . import notification_registry as contracts
from .models import Input
from .transactions import run
from .notifications import emit_system_notification_test
from .config import LIMITS
from .content import invalid

router = APIRouter(
    prefix="/api/v1/notification-administration",
    tags=["notification administration"],
    dependencies=[Depends(require_global_privilege(config.ADMIN))],
)


class Preview(Input):
    configuration: config.Configuration
    context: dict = Field(default_factory=dict)


class TestSend(Input):
    test_run_id: UUID
    configuration_version_id: UUID
    context: dict = Field(default_factory=dict)
    recipient_user_ids: list[StrictInt] = Field(
        min_length=1, max_length=LIMITS["TEST_MAX_RECIPIENTS"]
    )


def execute(principal, operation):
    def checked(c):
        config.require_admin(c, principal.user_id)
        return operation(c)

    return run(principal.user_id, checked)


@router.get("/producers")
def producers(
    q: str = Query("", max_length=120),
    after: str = Query("", max_length=120),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def operation(c):
        language = preferred_language_for_user(c, principal.user_id)
        rows = c.execute(
            """SELECT p.*,v.version AS active_version,v.enabled,v.operational_owner FROM system_notification_producers p LEFT JOIN system_notification_configuration_versions v ON v.id=p.active_configuration_version_id WHERE p.producer_code>%s AND (p.producer_code ILIKE %s OR p.feature_code ILIKE %s OR p.name ILIKE %s OR COALESCE(p.translations->%s->>'name',p.translations->%s->>'name',p.name) ILIKE %s) ORDER BY p.producer_code LIMIT %s""",
            (
                after,
                "%" + q + "%",
                "%" + q + "%",
                "%" + q + "%",
                language,
                language.split("-", 1)[0],
                "%" + q + "%",
                limit + 1,
            ),
        ).fetchall()
        return {
            "items": localize_rows(rows[:limit], language, "name"),
            "next_cursor": (
                rows[limit - 1]["producer_code"] if len(rows) > limit else None
            ),
        }

    return execute(principal, operation)


@router.get("/recipients/{kind}")
def recipients(
    kind: str,
    q: str = Query("", max_length=120),
    target_id: int | None = Query(None, gt=0),
    after: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def operation(c):
        if kind not in {"user", "role", "org_unit"}:
            invalid("notification_audience_invalid")
        table = {"user": "users", "role": "roles", "org_unit": "org_units"}[kind]
        live = {
            "user": "status='active' AND account_type='person' AND messaging_user_clearance(id)>=(SELECT min(level_number) FROM security_levels)",
            "role": "role_effectively_active(id)",
            "org_unit": "org_unit_effectively_active(id)",
        }[kind]
        rows = c.execute(
            f"SELECT id,name FROM {table} WHERE {live} AND id>%s AND (%s::bigint IS NULL OR id=%s) AND name ILIKE %s ORDER BY id LIMIT %s",
            (after, target_id, target_id, "%" + q + "%", limit + 1),
        ).fetchall()
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    return execute(principal, operation)


@router.get("/producers/{code}")
def producer(code: str, principal: Principal = Depends(principal_from_request)):
    def operation(c):
        definition = contracts.registry.get(code)
        row = config.state(c, code)
        return {
            **row,
            "localized": localized_projection(
                row, preferred_language_for_user(c, principal.user_id), "name"
            ),
            "sample_context": definition.sample_context,
            "languages": config.enabled_languages(c),
            "registered_languages": c.execute(
                "SELECT language_tag,direction,is_enabled FROM supported_languages ORDER BY language_tag"
            ).fetchall(),
            "limits": {
                key: value for key, value in LIMITS.items() if key.startswith("TEST_")
            },
        }

    return execute(principal, operation)


@router.get("/producers/{code}/versions")
def versions(
    code: str,
    before: int = Query(2147483647, ge=1),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def operation(c):
        rows = c.execute(
            "SELECT id,version,enabled,operational_owner,created_at,created_by_user_id FROM system_notification_configuration_versions WHERE producer_code=%s AND version<%s ORDER BY version DESC LIMIT %s",
            (code, before, limit + 1),
        ).fetchall()
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["version"] if len(rows) > limit else None,
        }

    return execute(principal, operation)


@router.get("/producers/{code}/versions/{identity}")
def version(
    code: str, identity: UUID, principal: Principal = Depends(principal_from_request)
):
    return execute(principal, lambda c: config.load_version(c, code, identity))


@router.post("/producers/{code}/preview")
def preview(
    code: str, payload: Preview, principal: Principal = Depends(principal_from_request)
):
    def operation(c):
        definition = contracts.registry.get(code)
        templates, _ = config.validate_configuration(
            c, definition, payload.configuration
        )
        return {
            "variants": config.render(
                c, definition, templates, payload.context, config.enabled_languages(c)
            )
        }

    return execute(principal, operation)


@router.post("/producers/{code}/versions")
def save(
    code: str,
    payload: config.Configuration,
    reason: str | None = Header(None, alias="X-Change-Reason"),
    principal: Principal = Depends(principal_from_request),
):
    return execute(
        principal,
        lambda c: config.save(
            c, principal.user_id, code, payload, decode_change_reason(reason)
        ),
    )


@router.post("/producers/{code}/versions/{identity}/activate")
def activate(
    code: str,
    identity: UUID,
    payload: config.Expected,
    reason: str | None = Header(None, alias="X-Change-Reason"),
    principal: Principal = Depends(principal_from_request),
):
    return execute(
        principal,
        lambda c: config.activate(
            c, principal.user_id, code, identity, payload, decode_change_reason(reason)
        ),
    )


@router.post("/producers/{code}/test")
def send_test(
    code: str, payload: TestSend, principal: Principal = Depends(principal_from_request)
):
    try:
        return execute(
            principal,
            lambda c: asdict(
                emit_system_notification_test(
                    transaction=c,
                    producer_code=code,
                    configuration_version_id=payload.configuration_version_id,
                    test_run_id=payload.test_run_id,
                    context=payload.context,
                    recipient_user_ids=payload.recipient_user_ids,
                    initiated_by_user_id=principal.user_id,
                )
            ),
        )
    except Exception as error:
        if not isinstance(error, HTTPException) or error.status_code != 403:
            execute(
                principal,
                lambda c: config.audit(
                    c,
                    principal.user_id,
                    "NOTIFICATION_TEST_FAILED",
                    code,
                    payload.configuration_version_id,
                    "Controlled notification test failed",
                    test_run_id=str(payload.test_run_id),
                    recipient_count=len(payload.recipient_user_ids),
                    result="failed",
                    is_test=True,
                ),
            )
        raise


@router.get("/producers/{code}/tests")
def history(
    code: str,
    before: int = Query(9223372036854775807, ge=1),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def operation(c):
        rows = c.execute(
            "SELECT id,occurred_at,actor_user_id,actor_name,correlation_id,metadata FROM event_history WHERE entity_type='system_notification' AND operation IN ('NOTIFICATION_TEST_SENT','NOTIFICATION_TEST_FAILED') AND metadata->>'producer_code'=%s AND id<%s ORDER BY id DESC LIMIT %s",
            (code, before, limit + 1),
        ).fetchall()
        return {
            "items": rows[:limit],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    return execute(principal, operation)
