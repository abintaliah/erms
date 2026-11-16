"""Owner-only mailbox lifecycle and bounded, atomic whole-conversation cleanup."""

from datetime import timedelta
from .config import LIMITS
from .content import invalid
from . import reading
from .service import level, require_exchange


def mailbox_change(c, user, kind, identity, restore=False):
    reading.person(c, user)
    if kind == "outbox":
        require_exchange(c, user)
        row = c.execute(
            "SELECT e.*,e.sender_deleted_at AS deleted_at,e.sender_purge_after AS purge_after FROM message_envelopes e WHERE id=%s AND sender_user_id=%s AND message_kind='user_message' FOR UPDATE",
            (identity, user),
        ).fetchone()
    else:
        row = c.execute(
            "SELECT e.*,d.deleted_at,d.purge_after,d.id AS delivery_id FROM message_envelopes e JOIN message_deliveries d ON d.envelope_id=e.id WHERE d.id=%s AND d.recipient_user_id=%s FOR UPDATE OF e,d",
            (identity, user),
        ).fetchone()
    if not row:
        invalid("message_not_found", 404)
    if row["sender_kind"] == "user":
        require_exchange(c, user)
    level(c, user, row["security_level_id"])
    now = c.execute("SELECT CURRENT_TIMESTAMP AS now").fetchone()["now"]
    expired = row["expires_at"] <= now
    deadline = row["purge_after"] or (
        row["expires_at"] + timedelta(days=row["expiry_restoration_days"])
        if expired
        else None
    )
    if deadline and deadline <= now:
        invalid("message_not_found", 404)
    if restore:
        if not row["deleted_at"] and not expired:
            return {"restored": True}
        # A pre-expiry restoration returns to ordinary expiry. After expiry the
        # existing deadline is immutable, including delete/restore repetitions.
        deleted = None
        deadline = deadline if expired else None
    else:
        if (
            row["message_kind"] == "user_message"
            and not expired
            and not c.execute(
                "SELECT 1 FROM message_record_captures x JOIN records r ON r.id=x.record_id WHERE x.selected_envelope_id=%s AND x.captured_by_user_id=%s",
                (row["id"], user),
            ).fetchone()
        ):
            invalid("message_capture_required", 409)
        deleted = row["deleted_at"] or now
        deadline = deadline or now + timedelta(days=LIMITS["DELETION_RECOVERY_DAYS"])
    if kind == "outbox":
        c.execute(
            "UPDATE message_envelopes SET sender_deleted_at=%s,sender_purge_after=%s WHERE id=%s",
            (deleted, deadline, row["id"]),
        )
    else:
        c.execute(
            "UPDATE message_deliveries SET deleted_at=%s,purge_after=%s,deletion_reason=%s WHERE id=%s",
            (
                deleted,
                deadline,
                (
                    None
                    if restore
                    else ("retention_expired" if expired else "user_deleted")
                ),
                identity,
            ),
        )
    return {"restored": restore, "restorable_until": deadline}


def deleted_listing(c, user, kind, limit, cursor=None):
    reading.person(c, user)
    if kind == "outbox":
        require_exchange(c, user)
        source = (
            "message_envelopes e JOIN security_levels l ON l.id=e.security_level_id"
        )
        projection = "e.*,l.level_number,l.name AS security_level_name,messaging_user_clearance(%s)>=l.level_number AS readable"
        owner = "e.sender_user_id=%s AND e.message_kind='user_message'"
        deleted, deadline, identity = (
            "e.sender_deleted_at",
            "e.sender_purge_after",
            "e.id",
        )
        args = [user, user]
    else:
        source, projection = reading.JOIN, reading.PROJECTION
        owner = "d.recipient_user_id=%s AND " + reading.VISIBLE
        deleted, deadline, identity = "d.deleted_at", "d.purge_after", "d.id"
        args = [user, user, user]
    condition = f"({deleted} IS NOT NULL OR (e.expires_at<=CURRENT_TIMESTAMP AND {deadline} IS NULL)) AND COALESCE({deadline},e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP"
    if cursor:
        condition += f" AND (e.sent_at,{identity})<(%s,%s)"
        args.extend(reading.cursor_decode(cursor))
    rows = c.execute(
        f"SELECT {projection},CURRENT_TIMESTAMP AS now,COALESCE({deadline},e.expires_at+make_interval(days=>e.expiry_restoration_days)) AS restorable_until FROM {source} WHERE {owner} AND {condition} ORDER BY e.sent_at DESC,{identity} DESC LIMIT %s",
        (*args, limit + 1),
    ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    items = reading.present(c, user, rows)
    for item, row in zip(items, rows):
        item["restorable_until"] = row["restorable_until"]
    return {
        "items": items,
        "has_more": more,
        "next_cursor": (
            reading.cursor_encode(rows[-1], "delivery_id" if kind == "inbox" else "id")
            if more
            else None
        ),
    }


# Recursive UNION deduplicates in PostgreSQL; Python never holds a group's bodies
# or member IDs. Every branch participates, including amendment notices.
GROUP_SQL = """WITH RECURSIVE edges AS (
 SELECT e.id,COALESCE(e.related_envelope_id,d.envelope_id,a.original_envelope_id) AS parent
 FROM message_envelopes e LEFT JOIN message_deliveries d ON d.id=e.related_delivery_id
 LEFT JOIN message_action_amendments a ON a.id=e.action_amendment_id
), members(id) AS (
 SELECT id FROM message_envelopes WHERE id=%s
 UNION
 SELECT CASE WHEN edges.id=members.id THEN edges.parent ELSE edges.id END
 FROM members JOIN edges ON edges.id=members.id OR edges.parent=members.id
 WHERE edges.parent IS NOT NULL
) SELECT id FROM members"""


def purge_group(c, root, snapshot=None):
    """Call in a fresh READ COMMITTED transaction; one group per transaction."""
    c.execute("SET LOCAL lock_timeout='3s'")
    c.execute("SET LOCAL statement_timeout='60s'")
    c.execute(
        "CREATE TEMP TABLE messaging_purge_candidates(id uuid PRIMARY KEY) ON COMMIT DROP"
    )
    c.execute("INSERT INTO messaging_purge_candidates " + GROUP_SQL, (root,))
    # A named server cursor bounds transfer while locking every envelope in a
    # stable order. Source sends/amendments lock their source envelope too.
    with c.cursor(name="messaging_group_locks") as cursor:
        cursor.execute(
            "SELECT e.id FROM message_envelopes e JOIN messaging_purge_candidates g ON g.id=e.id ORDER BY e.id FOR UPDATE OF e"
        )
        while cursor.fetchmany(LIMITS["CLEANUP_BATCH_SIZE"]):
            pass
    changed = c.execute(
        "SELECT EXISTS(("
        + GROUP_SQL
        + ") EXCEPT SELECT id FROM messaging_purge_candidates) AS changed",
        (root,),
    ).fetchone()["changed"]
    if changed:
        return 0
    c.execute(
        "DELETE FROM messaging_cleanup_groups WHERE group_key IN(SELECT id FROM messaging_purge_candidates) AND group_key<>(SELECT id FROM messaging_purge_candidates ORDER BY id LIMIT 1)"
    )
    c.execute(
        """INSERT INTO messaging_cleanup_groups(group_key,member_count,expired_count,eligible_at)
 SELECT (SELECT id FROM messaging_purge_candidates ORDER BY id LIMIT 1),count(*),count(*) FILTER(WHERE e.expires_at<=CURRENT_TIMESTAMP),
 max(GREATEST(e.expires_at,CASE WHEN e.sender_kind='user' THEN COALESCE(e.sender_purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days)) ELSE e.expires_at END,
 (SELECT max(COALESCE(d.purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))) FROM message_deliveries d WHERE d.envelope_id=e.id)))
 FROM message_envelopes e JOIN messaging_purge_candidates g ON g.id=e.id HAVING count(*)>0
 ON CONFLICT(group_key) DO UPDATE SET member_count=EXCLUDED.member_count,expired_count=EXCLUDED.expired_count,eligible_at=EXCLUDED.eligible_at,observed_at=CURRENT_TIMESTAMP"""
    )
    if snapshot is not None:
        row = c.execute(
            "SELECT * FROM messaging_cleanup_groups WHERE group_key=(SELECT id FROM messaging_purge_candidates ORDER BY id LIMIT 1)"
        ).fetchone()
        if row:
            snapshot.update(row)
    ineligible = c.execute(
        """SELECT EXISTS(SELECT 1 FROM message_envelopes e JOIN messaging_purge_candidates g ON g.id=e.id
 WHERE e.expires_at>CURRENT_TIMESTAMP
 OR (e.sender_kind='user' AND COALESCE(e.sender_purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP)
 OR EXISTS(SELECT 1 FROM message_deliveries d WHERE d.envelope_id=e.id AND COALESCE(d.purge_after,e.expires_at+make_interval(days=>e.expiry_restoration_days))>CURRENT_TIMESTAMP)) AS blocked"""
    ).fetchone()["blocked"]
    if ineligible:
        return 0
    c.execute(
        "CREATE TEMP TABLE messaging_purge_members(id uuid PRIMARY KEY) ON COMMIT DROP"
    )
    c.execute(
        "INSERT INTO messaging_purge_members SELECT id FROM messaging_purge_candidates"
    )
    c.execute(
        "UPDATE message_request_receipts SET result_purged_at=CURRENT_TIMESTAMP WHERE result_envelope_id IN(SELECT id FROM messaging_purge_members) AND result_purged_at IS NULL"
    )
    for table, column in [
        ("message_action_completions", "reply_envelope_id"),
        ("message_action_amendments", "original_envelope_id"),
        ("message_envelope_localizations", "envelope_id"),
        ("message_recipient_selectors", "envelope_id"),
        ("message_resource_links", "envelope_id"),
        ("message_deliveries", "envelope_id"),
        ("message_addressees", "envelope_id"),
    ]:
        c.execute(
            f"DELETE FROM {table} WHERE {column} IN(SELECT id FROM messaging_purge_members)"
        )
    c.execute(
        "DELETE FROM messaging_cleanup_groups WHERE group_key IN(SELECT id FROM messaging_purge_members)"
    )
    return c.execute(
        "DELETE FROM message_envelopes WHERE id IN(SELECT id FROM messaging_purge_members)"
    ).rowcount


def cleanup_drafts(c):
    rows = c.execute(
        """SELECT id FROM message_drafts
 WHERE COALESCE(purge_after,expires_at+make_interval(days=>expiry_restoration_days))<=CURRENT_TIMESTAMP
 ORDER BY expires_at,id LIMIT %s FOR UPDATE SKIP LOCKED""",
        (LIMITS["CLEANUP_BATCH_SIZE"],),
    ).fetchall()
    ids = [row["id"] for row in rows]
    for table in ("message_draft_recipient_selectors", "message_draft_resource_links"):
        c.execute(f"DELETE FROM {table} WHERE draft_id=ANY(%s::uuid[])", (ids,))
    return c.execute(
        "DELETE FROM message_drafts WHERE id=ANY(%s::uuid[])", (ids,)
    ).rowcount


def deleted_detail(c, user, kind, identity):
    reading.person(c, user)
    if kind == "outbox":
        require_exchange(c, user)
        row = c.execute(
            "SELECT e.*,l.level_number,l.name AS security_level_name,e.sender_deleted_at AS deleted_at,e.sender_purge_after AS purge_after,messaging_user_clearance(%s)>=l.level_number AS readable,CURRENT_TIMESTAMP AS now FROM message_envelopes e JOIN security_levels l ON l.id=e.security_level_id WHERE e.id=%s AND e.sender_user_id=%s AND e.message_kind='user_message'",
            (user, identity, user),
        ).fetchone()
    else:
        row = c.execute(
            f"SELECT {reading.PROJECTION},d.deleted_at,d.purge_after,CURRENT_TIMESTAMP AS now FROM {reading.JOIN} WHERE d.id=%s AND d.recipient_user_id=%s AND {reading.VISIBLE}",
            (user, identity, user, user),
        ).fetchone()
    if not row:
        invalid("message_not_found", 404)
    deadline = row["purge_after"] or row["expires_at"] + timedelta(
        days=row["expiry_restoration_days"]
    )
    if deadline <= row["now"] or (
        not row["deleted_at"] and (row["expires_at"] > row["now"] or row["purge_after"])
    ):
        invalid("message_not_found", 404)
    result = reading.present(c, user, [row], detail=True)[0]
    result["restorable_until"] = deadline
    return result
