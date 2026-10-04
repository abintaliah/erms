"""Approved legal-hold producers; no hold names or resource contents in messages."""

from datetime import timezone

from .messaging.notification_registry import SystemNotificationDefinition, Placeholder
from .messaging.models import Selector
from .messaging.config import LIMITS
from .messaging.notifications import emit_system_notification

ASSIGNED = "holds.responsibility_assigned"
ENDING = "holds.approaching_end"


def _people(c, hold_id):
    return c.execute(
        """SELECT DISTINCT u.id FROM users u WHERE u.status='active'
        AND u.account_type='person' AND (u.id=(SELECT owner_user_id FROM holds WHERE id=%s)
        OR EXISTS(SELECT 1 FROM hold_contributors hc WHERE hc.hold_id=%s AND hc.user_id=u.id))
        ORDER BY u.id LIMIT %s""",
        (hold_id, hold_id, LIMITS["MAX_SELECTORS_PER_SEND"] + 1),
    ).fetchall()


def assigned_audience(c, context):
    row = c.execute(
        """SELECT u.id FROM users u WHERE u.id=%s AND u.status='active'
        AND u.account_type='person' AND (EXISTS(SELECT 1 FROM holds WHERE id=%s AND owner_user_id=u.id)
        OR EXISTS(SELECT 1 FROM hold_contributors WHERE hold_id=%s AND user_id=u.id))""",
        (context["user_id"], context["hold_id"], context["hold_id"]),
    ).fetchone()
    return [Selector(selector_kind="user", target_id=row["id"])] if row else []


def ending_audience(c, context):
    return [
        Selector(selector_kind="user", target_id=r["id"])
        for r in _people(c, context["hold_id"])
    ]


def definitions():
    return (
        SystemNotificationDefinition(
            producer_code=ASSIGNED,
            feature_code="holds",
            event_type="responsibility_assigned",
            contract_version=1,
            required_for_business_commit=False,
            allow_static_audience=False,
            placeholders={
                "hold_id": Placeholder(type="integer"),
                "user_id": Placeholder(type="integer"),
            },
            audience_resolvers={"newly_assigned_person": assigned_audience},
            sample_context={"hold_id": 1, "user_id": 1},
        ),
        SystemNotificationDefinition(
            producer_code=ENDING,
            feature_code="holds",
            event_type="approaching_end",
            contract_version=1,
            required_for_business_commit=False,
            allow_static_audience=False,
            placeholders={
                "hold_id": Placeholder(type="integer"),
                "end_date": Placeholder(type="datetime"),
            },
            audience_resolvers={"current_responsible_people": ending_audience},
            sample_context={"hold_id": 1, "end_date": "2030-01-08T00:00:00+00:00"},
        ),
    )


def configured(c, code):
    # Optional built-ins are dormant until an administrator activates a configuration.
    return bool(
        c.execute(
            "SELECT 1 FROM system_notification_producers WHERE producer_code=%s AND active_configuration_version_id IS NOT NULL",
            (code,),
        ).fetchone()
    )


def notify_assignments(c, hold_id, user_ids, actor):
    if not user_ids or not configured(c, ASSIGNED):
        return
    # One event per newly assigned person avoids disclosing other responsible people.
    event = c.execute(
        "SELECT id FROM event_history WHERE entity_type='hold' AND entity_id=%s ORDER BY id DESC LIMIT 1",
        (hold_id,),
    ).fetchone()["id"]
    for user_id in sorted(set(user_ids)):
        emit_system_notification(
            transaction=c,
            producer_code=ASSIGNED,
            source_event_id=f"{event}:{user_id}",
            context={"hold_id": hold_id, "user_id": user_id},
            triggered_by_user_id=actor,
        )


def process_reminders(c, limit=100):
    """One bounded transaction. Caller provides a repeatable/serializable snapshot."""
    if not configured(c, ENDING):
        return 0
    enabled = c.execute(
        """SELECT v.enabled FROM system_notification_producers p
        JOIN system_notification_configuration_versions v ON v.id=p.active_configuration_version_id
        WHERE p.producer_code=%s""",
        (ENDING,),
    ).fetchone()
    if not enabled["enabled"]:
        return 0
    rows = c.execute(
        """SELECT h.id,h.valid_to FROM holds h
        WHERE h.valid_from<=CURRENT_TIMESTAMP AND h.valid_to>CURRENT_TIMESTAMP
        AND h.valid_to<=CURRENT_TIMESTAMP+interval '7 days'
        AND EXISTS(SELECT 1 FROM users u WHERE u.status='active' AND u.account_type='person'
            AND (u.id=h.owner_user_id OR EXISTS(SELECT 1 FROM hold_contributors hc
                WHERE hc.hold_id=h.id AND hc.user_id=u.id)))
        AND NOT EXISTS(SELECT 1 FROM hold_notification_reminders n WHERE n.hold_id=h.id AND n.end_at=h.valid_to)
        ORDER BY h.valid_to,h.id LIMIT %s FOR UPDATE OF h SKIP LOCKED""",
        (limit,),
    ).fetchall()
    sent = 0
    for hold in rows:
        if not _people(c, hold["id"]):
            continue
        end = hold["valid_to"].astimezone(timezone.utc).isoformat()
        outcome = emit_system_notification(
            transaction=c,
            producer_code=ENDING,
            source_event_id=f"{hold['id']}:{end}",
            context={"hold_id": hold["id"], "end_date": hold["valid_to"]},
        )
        if outcome.status != "disabled":
            c.execute(
                "INSERT INTO hold_notification_reminders(hold_id,end_at) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (hold["id"], hold["valid_to"]),
            )
            sent += 1
    return sent


def reminder_tick():
    from .database import pool

    with pool.connection() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        c.execute("SET LOCAL lock_timeout = '3s'")
        c.execute("SET LOCAL statement_timeout = '60s'")
        c.execute(
            "SELECT set_config('app.actor_type','automated_process',true),set_config('app.event_source','system',true)"
        )
        # Other API instances skip this tick. The durable pair key survives restarts.
        if not c.execute(
            "SELECT pg_try_advisory_xact_lock(482019038) AS locked"
        ).fetchone()["locked"]:
            return 0
        return process_reminders(c)
