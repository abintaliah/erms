"""Relationship grants travel only backwards from an owned mailbox entry."""

from .content import invalid
from .service import level, require_exchange
from .reading import ACTIVE_INBOX, ACTIVE_OUTBOX, present


def validate_source(c, user, payload):
    kind = payload.relationship_kind
    delivery = payload.related_delivery_id
    envelope = payload.related_envelope_id
    if kind is None:
        if delivery or envelope or payload.complete_action:
            invalid("message_relationship_invalid")
        return None
    if (
        (kind == "reply" and (not delivery or envelope))
        or (kind == "follow_up" and (delivery or not envelope))
        or (kind == "forward" and bool(delivery) == bool(envelope))
    ):
        invalid("message_relationship_invalid")
    if payload.complete_action and kind != "reply":
        invalid("message_completion_requires_reply")
    if delivery:
        row = c.execute(
            f"""SELECT e.*,l.level_number FROM message_envelopes e
            JOIN message_deliveries d ON d.envelope_id=e.id JOIN security_levels l ON l.id=e.security_level_id
            WHERE d.id=%s AND d.recipient_user_id=%s AND {ACTIVE_INBOX} AND e.expires_at>CURRENT_TIMESTAMP
            FOR UPDATE OF e,d""",
            (delivery, user),
        ).fetchone()
    else:
        row = c.execute(
            f"""SELECT e.*,l.level_number FROM message_envelopes e JOIN security_levels l ON l.id=e.security_level_id
            WHERE e.id=%s AND e.sender_user_id=%s AND {ACTIVE_OUTBOX} AND e.expires_at>CURRENT_TIMESTAMP
            FOR UPDATE OF e""",
            (envelope, user),
        ).fetchone()
    if not row:
        invalid("message_source_unavailable", 404)
    if row["is_test"] or row["message_kind"] == "action_amendment_notice":
        invalid("message_source_ineligible")
    level(c, user, row["security_level_id"])
    return row


def linked(c, user, root, target):
    require_exchange(c, user)
    # A root UUID is accepted only with this user's own active/restorable entry.
    root_row = c.execute(
        """SELECT e.* FROM message_envelopes e WHERE e.id=%s AND
        ((e.sender_user_id=%s AND ((e.sender_deleted_at IS NULL AND e.expires_at>CURRENT_TIMESTAMP) OR COALESCE(e.sender_purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP))
        OR EXISTS(SELECT 1 FROM message_deliveries d WHERE d.envelope_id=e.id AND d.recipient_user_id=%s
            AND ((d.deleted_at IS NULL AND e.expires_at>CURRENT_TIMESTAMP) OR COALESCE(d.purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP)))""",
        (root, user, user),
    ).fetchone()
    if not root_row:
        invalid("message_not_found", 404)
    # Recursive ancestry is bounded by the actual retained chain, never traverses
    # descendants/siblings, and stops cycles. Only the requested row is returned.
    access = c.execute(
        """WITH RECURSIVE ancestors AS (
        SELECT e.id,e.related_envelope_id,e.related_delivery_id,e.action_amendment_id,e.security_level_id,ARRAY[e.id] AS visited
        FROM message_envelopes e WHERE e.id=%s
        UNION ALL
        SELECT parent.id,parent.related_envelope_id,parent.related_delivery_id,parent.action_amendment_id,parent.security_level_id,a.visited||parent.id
        FROM ancestors a
        LEFT JOIN message_deliveries source ON source.id=a.related_delivery_id
        LEFT JOIN message_action_amendments amendment ON amendment.id=a.action_amendment_id
        JOIN message_envelopes parent ON parent.id=COALESCE(a.related_envelope_id,source.envelope_id,amendment.original_envelope_id)
        WHERE NOT parent.id=ANY(a.visited) AND a.id<>%s
        ) SELECT bool_or(a.id=%s) AS found,bool_and(messaging_user_clearance(%s)>=l.level_number) AS readable
        FROM ancestors a JOIN security_levels l ON l.id=a.security_level_id""",
        (root, target, target, user),
    ).fetchone()
    if not access["found"] or not access["readable"]:
        invalid("message_not_found", 404)
    row = c.execute(
        "SELECT e.*,l.level_number,l.name AS security_level_name,true AS readable,CURRENT_TIMESTAMP AS now FROM message_envelopes e JOIN security_levels l ON l.id=e.security_level_id WHERE e.id=%s",
        (target,),
    ).fetchone()
    result = present(c, user, [row], detail=True)[0]
    result["read_only_relationship"] = True
    return result
