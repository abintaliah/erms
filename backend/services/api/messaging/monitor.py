"""Sanitized operational read model; no mailbox/content permission is implied."""

from ..entity_localization import localize_rows, preferred_language_for_user
from fastapi import APIRouter, Depends, Query
from ..authentication import Principal, principal_from_request
from ..authorization_policy import require_global_privilege
from ..resource_authorization import require_global
from .transactions import run
from .config import LIMITS
from .gateway_health import CURRENT_REPORT_SQL, HEALTH_STATUS_SQL

router = APIRouter(
    prefix="/api/v1/messages/monitor",
    tags=["messages"],
    dependencies=[Depends(require_global_privilege("messaging.monitor"))],
)


@router.get("")
def overview(principal: Principal = Depends(principal_from_request)):
    def query(c):
        require_global(c, "messaging.monitor")
        metrics = c.execute(
            "SELECT metric,sum(value) AS value,sum(observations) AS observations,min(unresolved_since) AS unresolved_since,max(last_observed_at) AS last_observed_at FROM messaging_operational_metrics GROUP BY metric ORDER BY metric"
        ).fetchall()
        retention = c.execute(
            """SELECT count(*) FILTER(WHERE expires_at>CURRENT_TIMESTAMP AND expires_at<=CURRENT_TIMESTAMP+make_interval(days=>%s)) AS approaching_expiry,
 count(*) FILTER(WHERE expires_at<=CURRENT_TIMESTAMP) AS expired_retained,
 min(expires_at) FILTER(WHERE expires_at+make_interval(days=>expiry_restoration_days)<=CURRENT_TIMESTAMP) AS oldest_expired_candidate
 FROM message_envelopes""",
            (LIMITS["RETENTION_WARNING_DAYS"],),
        ).fetchone()
        groups = c.execute(
            "SELECT COALESCE(sum(member_count),0) AS group_members,COALESCE(sum(expired_count) FILTER(WHERE eligible_at>CURRENT_TIMESTAMP),0) AS expired_retained_by_group,count(*) FILTER(WHERE eligible_at<=CURRENT_TIMESTAMP) AS eligible_groups,min(eligible_at) FILTER(WHERE eligible_at<=CURRENT_TIMESTAMP) AS oldest_eligible_group,max(member_count) AS largest_group,sum(failure_count) AS group_failures FROM messaging_cleanup_groups"
        ).fetchone()
        entries = c.execute(
            """SELECT count(*) FILTER(WHERE d.deleted_at IS NULL AND (e.expires_at>CURRENT_TIMESTAMP OR d.purge_after>CURRENT_TIMESTAMP)) AS active_inbox,
 count(*) FILTER(WHERE (d.deleted_at IS NOT NULL OR (e.expires_at<=CURRENT_TIMESTAMP AND d.purge_after IS NULL)) AND COALESCE(d.purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP) AS restorable_inbox
 FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id"""
        ).fetchone()
        outbox = c.execute(
            """SELECT count(*) FILTER(WHERE sender_deleted_at IS NULL AND (expires_at>CURRENT_TIMESTAMP OR sender_purge_after>CURRENT_TIMESTAMP)) AS active_outbox,
 count(*) FILTER(WHERE (sender_deleted_at IS NOT NULL OR (expires_at<=CURRENT_TIMESTAMP AND sender_purge_after IS NULL)) AND COALESCE(sender_purge_after,expires_at+make_interval(days=>expiry_restoration_days))>CURRENT_TIMESTAMP) AS restorable_outbox FROM message_envelopes WHERE sender_user_id IS NOT NULL"""
        ).fetchone()
        gateways = c.execute(
            f"SELECT count(*) AS instances,count(*) FILTER(WHERE NOT listener_connected OR observed_at<CURRENT_TIMESTAMP-interval '45 seconds') AS unhealthy FROM messaging_gateway_health WHERE {CURRENT_REPORT_SQL}"
        ).fetchone()
        return {
            "metrics": metrics,
            "retention": {**retention, **entries, **outbox, **groups},
            "gateways": gateways,
            # Gateway alerts travel with their bounded gateway page, including
            # endpoint identity, rather than an unbounded overview collection.
            "alerts": (
                [
                    {
                        "code": "messaging_operation_failure",
                        "metric": r["metric"],
                        "since": r["unresolved_since"],
                    }
                    for r in metrics
                    if r["unresolved_since"]
                ]
            )
            + (
                [
                    {
                        "code": "messaging_group_cleanup_delayed",
                        "metric": "delayed_groups",
                    }
                ]
                if groups["group_failures"]
                else []
            ),
            "can_view_audit": c.execute(
                "SELECT user_has_global_privilege(%s,'audit.view') AS allowed",
                (principal.user_id,),
            ).fetchone()["allowed"],
        }

    return run(principal.user_id, query)


@router.get("/gateways")
def gateways(
    after: str = Query("", max_length=36),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def query(c):
        require_global(c, "messaging.monitor")
        rows = c.execute(
            f"SELECT *, {HEALTH_STATUS_SQL} AS health_status FROM messaging_gateway_health WHERE {CURRENT_REPORT_SQL} AND instance_id::text>%s ORDER BY instance_id::text LIMIT %s",
            (after, limit + 1),
        ).fetchall()
        for row in rows:
            row["host_addresses"] = [str(a) for a in (row["host_addresses"] or [])]
        return {
            "items": rows[:limit],
            "next_cursor": (
                str(rows[limit - 1]["instance_id"]) if len(rows) > limit else None
            ),
        }

    return run(principal.user_id, query)


@router.get("/producers")
def producers(
    after: str = Query("", max_length=120),
    limit: int = Query(25, ge=1, le=50),
    principal: Principal = Depends(principal_from_request),
):
    def query(c):
        require_global(c, "messaging.monitor")
        codes = c.execute(
            "SELECT DISTINCT producer_code FROM messaging_operational_metrics WHERE producer_code<>'' AND producer_code>%s ORDER BY producer_code LIMIT %s",
            (after, limit + 1),
        ).fetchall()
        selected = [r["producer_code"] for r in codes[:limit]]
        rows = c.execute(
            "SELECT m.producer_code,p.name,p.translations,m.metric,m.value,m.observations,m.last_observed_at,m.unresolved_since FROM messaging_operational_metrics m LEFT JOIN system_notification_producers p ON p.producer_code=m.producer_code WHERE m.producer_code=ANY(%s) ORDER BY m.producer_code,m.metric",
            (selected,),
        ).fetchall()
        return {
            "items": localize_rows(
                rows, preferred_language_for_user(c, principal.user_id), "name"
            ),
            "next_cursor": selected[-1] if len(codes) > limit else None,
        }

    return run(principal.user_id, query)
