"""Message preservation through the existing authoritative record-draft commit."""

from datetime import timezone
from hashlib import sha256
from html import escape
from io import BytesIO
import re
from time import monotonic
from uuid import uuid4
from fastapi import UploadFile
from ..resource_authorization import require_global, require_resource_operation
from ..entity_localization import preferred_language_for_user, localized_projection
from ..content_storage import configured_storage
from . import reading, relationships, capture_pdf
from .content import body, invalid
from .config import LIMITS
from .service import level, require_exchange
from .notification_configuration import localized_labels


def sources(c, user, selected, root):
    require_exchange(c, user)
    # Relationship authorization checks every intervening clearance, starting
    # from an owned active/restorable entry. It never traverses other branches.
    relationships.linked(c, user, root, selected)
    rows = []
    visited = set()
    identity = selected
    while identity:
        if identity in visited:
            invalid("message_capture_integrity", 409)
        if len(rows) > LIMITS["CAPTURE_MAX_LINKED_MESSAGES"]:
            invalid("message_capture_chain_limit", 413)
        visited.add(identity)
        row = c.execute(
            "SELECT e.*,l.level_number,l.name AS security_level_name,CURRENT_TIMESTAMP AS now FROM message_envelopes e JOIN security_levels l ON l.id=e.security_level_id WHERE e.id=%s FOR UPDATE OF e",
            (identity,),
        ).fetchone()
        if not row:
            invalid("message_not_found", 404)
        level(c, user, row["security_level_id"])
        if row["message_kind"] != "user_message":
            invalid("message_capture_kind_ineligible", 409)
        rows.append(row)
        identity = row["related_envelope_id"]
        if row["related_delivery_id"]:
            parent = c.execute(
                "SELECT envelope_id FROM message_deliveries WHERE id=%s",
                (row["related_delivery_id"],),
            ).fetchone()
            if not parent:
                invalid("message_capture_integrity", 409)
            identity = parent["envelope_id"]
    return [rows[0]] + sorted(rows[1:], key=lambda r: (r["sent_at"], r["id"]))


def preview(c, user, selected, root=None):
    """Read an authorized manifest; create no draft, files or conversion job."""
    require_global(c, "record.create")
    rows = sources(c, user, selected, root or selected)
    highest = max(rows, key=lambda r: r["level_number"])
    return {
        "title": rows[0]["subject"], "date_originated": rows[0]["sent_at"],
        "security_level_id": highest["security_level_id"], "medium": "digital",
        "components": [{"file_name": filename(row), "title": row["subject"]} for row in rows],
    }


def initialize(c, user, selected, root=None):
    require_global(c, "record.create")
    rows = sources(c, user, selected, root or selected)
    tag = preferred_language_for_user(c, user)
    lang = c.execute(
        "SELECT direction FROM supported_languages WHERE language_tag=%s", (tag,)
    ).fetchone()
    highest = max(rows, key=lambda r: r["level_number"])
    draft = c.execute(
        """INSERT INTO record_drafts(owner_user_id,title,date_originated,security_level_id,medium)
 VALUES(%s,%s,%s,%s,'digital') RETURNING *""",
        (user, rows[0]["subject"], rows[0]["sent_at"], highest["security_level_id"]),
    ).fetchone()
    c.execute(
        "INSERT INTO message_capture_drafts VALUES(%s,%s,%s,%s,%s,%s)",
        (
            draft["id"],
            uuid4(),
            selected,
            root or selected,
            tag,
            lang["direction"] if lang else "ltr",
        ),
    )
    # The same renderer runs again under commit locks, capturing intervening
    # amendments faithfully; staged files are never treated as authorization.
    stage_messages(c, draft, rows, tag, lang["direction"] if lang else "ltr")
    return draft


def validate_medium(c, draft_id, medium):
    if capture_draft(c, draft_id) and medium != "digital":
        invalid("message_capture_medium_fixed_digital", 409)


def capture_draft(c, identity):
    return c.execute(
        "SELECT * FROM message_capture_drafts WHERE draft_id=%s", (identity,)
    ).fetchone()


def protect_components(c, identity):
    if capture_draft(c, identity):
        invalid("message_capture_components_fixed", 409)


def prepare(c, draft):
    capture = capture_draft(c, draft["id"])
    if not capture:
        return None
    rows = sources(
        c,
        draft["owner_user_id"],
        capture["selected_envelope_id"],
        capture["root_envelope_id"],
    )
    configured = level(c, draft["owner_user_id"], draft["security_level_id"])
    if configured["level_number"] < max(r["level_number"] for r in rows):
        invalid("message_capture_security_floor", 409)
    if draft["medium"] != "digital":
        invalid("message_capture_medium_fixed_digital", 409)
    capture["rows"] = rows
    capture["captured_at"] = c.execute("SELECT CURRENT_TIMESTAMP AS t").fetchone()["t"]
    capturer = c.execute(
        "SELECT name,translations FROM users WHERE id=%s", (draft["owner_user_id"],)
    ).fetchone()
    capture["captured_by_name"] = localized_projection(
        capturer, capture["language_tag"], "name"
    )["name"]
    return capture


def labels(c, tag):
    keys = [
        "sender",
        "sent_at",
        "to",
        "cc",
        "priority",
        "security",
        "action",
        "due",
        "body",
        "amendments",
        "resources",
        "unavailable",
        "provenance",
        "capture_id",
        "record_id",
        "record_number",
        "selected",
        "captured_at",
        "captured_by",
        "components",
        "linked",
        "filename",
        "envelope_id",
        "order",
        "none",
        "previous",
        "new",
        "effective",
    ]
    result = {}
    for key in keys:
        translated = localized_labels(c, "messaging.capture." + key)
        result[key] = translated.get(tag, translated.get("en", key))
    return result


def field(label, value):
    return (
        f'<p class="field"><strong>{escape(label)}:</strong> {escape(str(value))}</p>'
    )


def message_pdf(c, row, tag, direction, text, deadline):
    headers = c.execute(
        """SELECT s.recipient_type,s.display_name,
            COALESCE(u.translations,r.translations,o.translations,'{}'::jsonb) AS translations
            FROM message_recipient_selectors s
            LEFT JOIN users u ON u.id=s.user_id
            LEFT JOIN roles r ON r.id=s.role_id
            LEFT JOIN org_units o ON o.id=s.org_unit_id
            WHERE s.envelope_id=%s ORDER BY s.recipient_type DESC,s.ordinal""",
        (row["id"],),
    ).fetchall()
    for header in headers:
        header["display_name"] = localized_projection(
            {"name": header["display_name"], "translations": header["translations"]}, tag, "name"
        )["name"]
    metadata = c.execute(
        """SELECT u.translations AS sender_translations,l.translations AS security_translations
            FROM message_envelopes e JOIN security_levels l ON l.id=e.security_level_id
            LEFT JOIN users u ON u.id=e.sender_user_id WHERE e.id=%s""",
        (row["id"],),
    ).fetchone()
    sender_name = localized_projection(
        {"name": row["sender_name"], "translations": metadata["sender_translations"]}, tag, "name"
    )["name"]
    security_name = localized_projection(
        {"name": row["security_level_name"], "translations": metadata["security_translations"]}, tag, "name"
    )["name"]
    links = c.execute(
        "SELECT * FROM message_resource_links WHERE envelope_id=%s ORDER BY ordinal",
        (row["id"],),
    ).fetchall()
    clean = body(row["body_rich_text"], [str(l["link_token"]) for l in links])
    readable = dict(row, readable=True)
    available = {
        str(l["link_token"]): l
        for l in reading.links_for(c, [readable]).get(row["id"], [])
    }
    for link in links:
        current = available[str(link["link_token"])]
        # The batched read projection checks current view permission and clearance.
        # Never disclose live metadata for an unavailable target or copy its content.
        if current["available"]:
            description = f"{current['number']} — {current['title']}"
        else:
            description = f"{link['resource_kind']} #{link['target_id_snapshot']} — {text['unavailable']}"
        clean = clean.replace(
            f'<span data-wathiq-link="{link["link_token"]}"></span>',
            f"<span>{escape(description)}</span>",
        )

    def localized(key):
        variants = localized_labels(c, key)
        return variants.get(tag, variants.get("en", key))

    output = "".join(
        field(text[k], v)
        for k, v in [
            ("sender", sender_name),
            ("sent_at", row["sent_at"].isoformat()),
            (
                "to",
                ", ".join(
                    h["display_name"] for h in headers if h["recipient_type"] == "to"
                ),
            ),
            (
                "cc",
                ", ".join(
                    h["display_name"] for h in headers if h["recipient_type"] == "cc"
                ),
            ),
            ("priority", localized("messaging.priority." + row["priority"])),
            ("security", security_name),
            (
                "action",
                localized("messaging.value." + str(row["action_required"]).lower()),
            ),
            (
                "due",
                (
                    f"{row['action_due_date']} · {row['action_due_timezone']} · {row['action_due_at'].isoformat()}"
                    if row["action_due_at"]
                    else text["none"]
                ),
            ),
        ]
    )
    output += f'<h2>{escape(text["body"])}</h2>' + clean
    amendments = c.execute(
        "SELECT * FROM message_action_amendments WHERE original_envelope_id=%s ORDER BY sequence",
        (row["id"],),
    ).fetchall()
    if amendments:
        output += f'<h2>{escape(text["amendments"])}</h2><ol>'
        for a in amendments:
            output += "<li>" + escape(
                f"{a['created_at'].isoformat()} · {a['created_by_user_id']} · {localized('messaging.amendment.'+a['amendment_kind'])} · {a['reason']}"
            )
            for prefix in ("previous", "new"):
                output += field(
                    text[prefix],
                    f"{localized('messaging.value.'+str(a[prefix+'_action_required']).lower())} · {a[prefix+'_due_date'] or text['none']} · {a[prefix+'_due_timezone'] or text['none']} · {a[prefix+'_due_at'] or text['none']}",
                )
            output += "</li>"
        output += "</ol>"
    effective = (
        amendments[-1]
        if amendments
        else dict(
            new_action_required=row["action_required"],
            new_due_date=row["action_due_date"],
            new_due_timezone=row["action_due_timezone"],
            new_due_at=row["action_due_at"],
        )
    )
    output += field(
        text["effective"],
        f"{localized('messaging.value.'+str(effective['new_action_required']).lower())} · {effective['new_due_date'] or text['none']} · {effective['new_due_timezone'] or text['none']} · {effective['new_due_at'] or text['none']}",
    )
    return capture_pdf.render(row["subject"], output, tag, direction, deadline=deadline)


def stage(c, draft_id, order, filename, data, originated):
    item = c.execute(
        """INSERT INTO record_draft_components(draft_id,component_order,file_name,date_originated,mime_type,size_in_bytes,checksum_algo,checksum_value,content_status)
 VALUES(%s,%s,%s,%s,'application/pdf',%s,'sha256',%s,'uploading') RETURNING id""",
        (draft_id, order, filename, originated, len(data), sha256(data).hexdigest()),
    ).fetchone()
    configured_storage().store_draft_upload(
        c, item["id"], UploadFile(file=BytesIO(data), filename=filename)
    )


def filename(row):
    return (
        "message-"
        + row["sent_at"].astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + str(row["id"])
        + ".pdf"
    )


def stage_messages(c, draft, rows, tag, direction, deadline=None):
    deadline = deadline or monotonic() + 600
    text = labels(c, tag)
    total = 0
    for order, row in enumerate(rows, 1):
        if monotonic() >= deadline:
            invalid("message_capture_renderer_unavailable", 503)
        data = message_pdf(c, row, tag, direction, text, deadline)
        total += len(data)
        if total > LIMITS["CAPTURE_MAX_PDF_BYTES"]:
            invalid("message_capture_pdf_limit", 413)
        stage(c, draft["id"], order, filename(row), data, row["sent_at"])
    return total


def finalize_staging(c, draft, record, capture):
    c.execute("DELETE FROM record_draft_components WHERE draft_id=%s", (draft["id"],))
    deadline = monotonic() + 600
    total = stage_messages(
        c,
        draft,
        capture["rows"],
        capture["language_tag"],
        capture["direction"],
        deadline,
    )
    text = labels(c, capture["language_tag"])
    content = "".join(
        field(text[k], v)
        for k, v in [
            ("capture_id", capture["capture_id"]),
            ("record_id", record["id"]),
            ("record_number", record["record_number"]),
            ("selected", capture["selected_envelope_id"]),
            ("captured_at", capture["captured_at"].isoformat()),
            (
                "captured_by",
                f"{capture['captured_by_name']} ({draft['owner_user_id']})",
            ),
        ]
    )
    content += f'<h2>{escape(text["components"])}</h2><ol>'
    for order, row in enumerate(capture["rows"], 1):
        content += (
            "<li>"
            + escape(
                f"{order} · {text['selected'] if order==1 else text['linked']} · {row['id']} · {row['sent_at'].isoformat()} · {filename(row)}"
            )
            + "</li>"
        )
    content += "</ol>"
    data = capture_pdf.render(
        text["provenance"],
        content,
        capture["language_tag"],
        capture["direction"],
        deadline=deadline,
    )
    if total + len(data) > LIMITS["CAPTURE_MAX_PDF_BYTES"]:
        invalid("message_capture_pdf_limit", 413)
    stage(
        c,
        draft["id"],
        len(capture["rows"]) + 1,
        "message-capture-provenance-" + str(capture["capture_id"]) + ".pdf",
        data,
        capture["captured_at"],
    )


def persist(c, draft, record, capture, components):
    c.execute(
        "INSERT INTO message_record_captures(id,selected_envelope_id,selected_envelope_id_at_capture,record_id,record_id_at_capture,captured_by_user_id,captured_by_name,captured_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            capture["capture_id"],
            capture["selected_envelope_id"],
            capture["selected_envelope_id"],
            record["id"],
            record["id"],
            draft["owner_user_id"],
            capture["captured_by_name"],
            capture["captured_at"],
        ),
    )
    for order, component in enumerate(components, 1):
        envelope = (
            capture["rows"][order - 1]["id"] if order <= len(capture["rows"]) else None
        )
        c.execute(
            """INSERT INTO message_record_capture_components(capture_id,component_kind,envelope_id,envelope_id_at_capture,digital_component_id,digital_component_id_at_capture,component_order,is_selected_message) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                capture["capture_id"],
                "message" if envelope else "provenance",
                envelope,
                envelope,
                component,
                component,
                order,
                order == 1,
            ),
        )


MESSAGING_MESSAGE_KEYS = (
    "messaging.capture.save",
    "messaging.capture.sender",
    "messaging.capture.sent_at",
    "messaging.capture.to",
    "messaging.capture.cc",
    "messaging.capture.priority",
    "messaging.capture.security",
    "messaging.capture.action",
    "messaging.capture.due",
    "messaging.capture.body",
    "messaging.capture.amendments",
    "messaging.capture.resources",
    "messaging.capture.unavailable",
    "messaging.capture.provenance",
    "messaging.capture.capture_id",
    "messaging.capture.record_id",
    "messaging.capture.record_number",
    "messaging.capture.selected",
    "messaging.capture.captured_at",
    "messaging.capture.captured_by",
    "messaging.capture.components",
    "messaging.capture.linked",
    "messaging.capture.filename",
    "messaging.capture.envelope_id",
    "messaging.capture.order",
    "messaging.capture.none",
    "messaging.capture.previous",
    "messaging.capture.new",
    "messaging.capture.effective",
)
