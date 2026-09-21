from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from nicegui import app, background_tasks, context, events, ui

from .api_client import ApiError, ErmsApiClient
from .capabilities import (
    capability_allowed,
    can_navigate,
    can_open_organization_detail,
    dashboard_administration_resources,
)
from .acl_editor import dependents_of, permission_closure
from .authorization_ui import (
    GATE_LABELS, OPERATIONS, acl_source_label, aggregation_reference_label,
    authorization_code_label, decision_code_label, operation_label, gate_detail, ordered_permission_catalogue,
    privilege_help_text, privilege_matches_search, security_level_label,
)
from .config import (
    api_url,
    dashboard_favourite_item_limit,
    dashboard_recent_days,
    dashboard_recent_item_limit,
    classification_recent_selection_limit,
    host,
    port,
    reload_enabled,
    storage_secret,
    user_details_session_limit,
)
from .entities import ENTITIES, EntitySpec, FieldSpec


app.add_static_files("/static/pdfjs", Path(__file__).with_name("static") / "pdfjs")
app.add_static_files("/static/brand", Path(__file__).with_name("static") / "brand")
app.add_static_files("/static/login", Path(__file__).with_name("static") / "login")

CLASSIFICATION_WORKSPACE_SEARCH_FIELDS = ("code", "title", "description", "keywords")
CLASSIFICATION_SELECTOR_SEARCH_FIELDS = ("code", "title", "description", "keywords")
CHILD_AGGREGATION_CLASSIFICATION_HELP = (
    "Child aggregations inherit classification governance from their root aggregation "
    "and cannot have a classification assigned directly."
)
RECORD_UPLOAD_WAIT_MESSAGE = "Please wait until all files have finished uploading."
AGGREGATION_SUMMARY_LAYOUT_CLASSES = (
    "detail-surface shadow-none flex-1 min-w-[360px] p-5 gap-4"
)
RECORD_DETAIL_HEADER_CLASSES = "w-full items-start gap-2 no-wrap"
RECORD_DETAIL_TITLE_CLASSES = "gap-0 grow min-w-0"
NAVIGATION_TRAIL_LIMIT = 20
NAVIGATION_VISIBLE_LIMIT = 5
STOP_PROPAGATION_CLICK_HANDLER = "(event) => { event.stopPropagation(); emit(); }"

SECURITY_EVENT_HELP = {
    "AUTHORIZATION_DENIED": "An operation was refused because one or more authorization gates did not pass.",
    "AUTHENTICATION_FAILED": "A sign-in attempt failed. Repeated failures can indicate an account or security problem.",
    "ACCOUNT_LOCKED": "An account was locked after reaching the configured failed sign-in threshold.",
    "INFORMATION_GOVERNANCE_BYPASS_USED": "A qualifying governance role bypassed the resource ACL; privilege and clearance checks still applied.",
    "ACCESS_EXPLANATION_VIEWED": "An authorized examiner inspected why another person was allowed or denied access.",
    "SECURITY_LEVEL_CHANGED": "A resource security level changed.",
    "SECURITY_LEVEL_UPGRADED": "A resource was raised to a more restrictive security level.",
    "SECURITY_LEVEL_DOWNGRADED": "A resource was lowered to a less restrictive security level.",
    "ACL_REPLACED": "A resource's local access-control list was replaced.",
    "DEFAULT_CHILD_AGGREGATION_ACL_REPLACED": "The default ACL inherited by child aggregations changed.",
    "DEFAULT_CHILD_RECORD_ACL_REPLACED": "The default ACL inherited by child records changed.",
    "PROFILE_PRIVILEGES_REPLACED": "The complete privilege set attached to a profile changed.",
    "PROFILE_ASSIGNED": "A role was assigned a different authorization profile.",
    "GOVERNANCE_ROLE_CHANGED": "A role's information-governance designation changed.",
}

AUTHORIZATION_DENIAL_HELP = (
    "These are operations refused by the authorization policy. A rise can indicate a missing "
    "profile privilege, expired assignment, insufficient clearance, missing ACL permission, "
    "an inactive account or organization relationship, or repeated unauthorized activity."
)


def navigation_entry_identity(entry: dict[str, Any]) -> tuple[str, int | None]:
    return str(entry["page"]), entry.get("entity_id")


def append_navigation_entry(
    trail: list[dict[str, Any]], entry: dict[str, Any],
    *, limit: int = NAVIGATION_TRAIL_LIMIT,
) -> list[dict[str, Any]]:
    """Append a page visit, collapsing only a consecutive logical duplicate."""
    updated = [dict(item) for item in trail]
    if updated and navigation_entry_identity(updated[-1]) == navigation_entry_identity(entry):
        updated[-1] = {**updated[-1], **entry}
    else:
        updated.append(dict(entry))
    return updated[-limit:]


def visible_navigation_indices(
    length: int, *, limit: int = NAVIGATION_VISIBLE_LIMIT,
) -> tuple[list[int], list[int]]:
    """Return visible and overflow indices while retaining first and recent pages."""
    if length <= limit:
        return list(range(length)), []
    recent_count = max(1, limit - 2)
    visible = [0, *range(length - recent_count - 1, length)]
    visible = sorted(set(visible))
    hidden = [index for index in range(length) if index not in visible]
    return visible, hidden
USER_AVATAR_COLORS = (
    "#2563eb", "#7c3aed", "#db2777", "#dc2626", "#ea580c",
    "#ca8a04", "#16a34a", "#0d9488", "#0891b2", "#4f46e5",
)
LIFECYCLE_ACTION_BUTTONS = (
    '<q-btn v-if="props.row.status === \'inactive\'" flat round dense '
    'icon="toggle_on" color="positive" aria-label="Activate" '
    '@click="$parent.$emit(\'lifecycle\', props.row)">'
    '<q-tooltip>Activate</q-tooltip></q-btn>'
    '<q-btn v-else flat round dense icon="toggle_off" color="negative" '
    'aria-label="Deactivate" @click="$parent.$emit(\'lifecycle\', props.row)">'
    '<q-tooltip>Deactivate</q-tooltip></q-btn>'
)
USER_SUSPENSION_ACTION_BUTTONS = (
    '<q-btn v-if="props.row.status !== \'suspended\'" flat round dense '
    'icon="pause_circle" color="warning" '
    ':disable="props.row.status !== \'active\'" '
    ':aria-label="props.row.status === \'active\' ? \'Suspend\' : \'Suspend unavailable while inactive\'" '
    '@click="$parent.$emit(\'suspend_user\', props.row)">'
    '<q-tooltip>{{ props.row.status === \'active\' ? \'Suspend\' : '
    "'Activate the user before suspending' }}</q-tooltip></q-btn>"
    '<q-btn v-else flat round dense icon="play_circle" color="positive" '
    'aria-label="Unsuspend" @click="$parent.$emit(\'unsuspend_user\', props.row)">'
    '<q-tooltip>Unsuspend</q-tooltip></q-btn>'
)


def favourite_preview(items: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    """Return a bounded Dashboard preview and whether more entries exist."""
    return items[:limit], len(items) > limit


def filter_membership_rows(
    rows: list[dict[str, Any]], *, query: str = "", status: str = "all",
    valid_from: str | None = None, valid_until: str | None = None,
) -> list[dict[str, Any]]:
    """Filter assignments by counterpart identity, status, and overlapping validity."""
    needle = query.strip().casefold()

    def date_part(value: Any) -> str | None:
        return str(value)[:10] if value else None

    def included(row: dict[str, Any]) -> bool:
        if needle and needle not in row.get("counterpart_search", "").casefold():
            return False
        if status != "all" and row.get("counterpart_status") != status:
            return False
        row_start = date_part(row.get("valid_from"))
        row_end = date_part(row.get("valid_until"))
        if valid_from and row_end and row_end < valid_from:
            return False
        if valid_until and row_start and row_start > valid_until:
            return False
        return True

    return [row for row in rows if included(row)]


def user_avatar(user: dict[str, Any]) -> dict[str, str]:
    """Return stable best-effort initials and color for a user."""
    parts = [part for part in str(user.get("name") or "").split() if part]
    if len(parts) >= 2:
        initials = f"{parts[0][0]}{parts[-1][0]}"
    elif parts:
        initials = parts[0][:2]
    else:
        initials = "?"
    stable_key = str(user.get("id") or user.get("email") or user.get("name") or "unknown")
    color_index = hashlib.sha256(stable_key.encode("utf-8")).digest()[0] % len(USER_AVATAR_COLORS)
    return {"initials": initials.upper(), "color": USER_AVATAR_COLORS[color_index]}


def render_user_avatar(user: dict[str, Any], *, size: str = "38px") -> Any:
    """Render the same deterministic avatar used by the Users listing."""
    avatar = user_avatar(user)
    with ui.avatar(size=size).style(
        f"background:{avatar['color']} !important;color:white !important"
    ) as control:
        ui.label(avatar["initials"]).classes("font-medium")
    return control


def display_value(value: Any) -> str:
    if value is None:
        return "—"
    return str(value)


def format_timestamp(value: Any) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y, %I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return str(value)


def format_file_size(value: Any) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(size)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def component_file_icon(mime_type: str | None) -> str:
    value = (mime_type or "").lower()
    if value == "application/pdf":
        return "picture_as_pdf"
    if value.startswith("image/"):
        return "image"
    if value.startswith("audio/"):
        return "audio_file"
    if value.startswith("video/"):
        return "video_file"
    if "spreadsheet" in value or "excel" in value or value == "text/csv":
        return "table_view"
    if "word" in value or "document" in value or value.startswith("text/"):
        return "description"
    return "draft"


def native_preview_kind(mime_type: str | None) -> str | None:
    value = (mime_type or "").lower()
    if value in {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/avif"}:
        return "image"
    if value.startswith("audio/"):
        return "audio"
    if value.startswith("video/"):
        return "video"
    return None


CONVERTIBLE_PREVIEW_EXTENSIONS = {
    ".doc", ".docx", ".odt", ".rtf",
    ".xls", ".xlsx", ".ods", ".csv",
    ".ppt", ".pptx", ".odp",
}


def requires_document_conversion(component: dict[str, Any]) -> bool:
    return (
        native_preview_kind(component.get("mime_type")) is None
        and (component.get("mime_type") or "").lower() != "application/pdf"
        and Path(component.get("file_name") or "").suffix.lower()
        in CONVERTIBLE_PREVIEW_EXTENSIONS
    )


def effective_closure(
    aggregation: dict[str, Any] | None,
    aggregations_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the nearest directly closed aggregation, including the item itself."""
    current = aggregation
    seen: set[int] = set()
    while current and current.get("id") not in seen:
        seen.add(current["id"])
        if current.get("date_closed"):
            return current
        current = aggregations_by_id.get(current.get("parent_aggregation_id"))
    return None


def inactive_org_unit_source(
    org_unit: dict[str, Any] | None,
    org_units_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any] | None:
    current = org_unit
    seen: set[int] = set()
    while current and current.get("id") not in seen:
        seen.add(current["id"])
        if current.get("status") == "inactive":
            return current
        current = org_units_by_id.get(current.get("parent_org_unit_id"))
    return None


def buffer_upload_batch(event: events.MultiUploadEventArguments) -> list[tuple[bytes, str, str]]:
    """Copy NiceGUI temporary uploads before any awaited API operation can release them."""
    return [
        (content_source.read(), name, mime_type or "application/octet-stream")
        for content_source, name, mime_type in zip(event.contents, event.names, event.types)
    ]


def render_component_cards(
    rows: list[dict[str, Any]], on_move, on_remove, on_history=None,
    on_view=None, on_download=None, *, readonly: bool = False,
    capabilities: dict[str, bool] | None = None,
) -> None:
    for index, component in enumerate(rows):
        status = component.get("content_status", "pending")
        status_color = {
            "available": "positive", "staged": "primary", "pending": "warning",
            "failed": "negative", "quarantined": "orange", "deleted": "grey",
        }.get(status, "grey")
        checksum = component.get("checksum_value") or "—"
        checksum_short = checksum if len(checksum) <= 18 else f"{checksum[:10]}…{checksum[-6:]}"
        with ui.card().classes("component-card w-full p-4 gap-3"):
            with ui.row().classes("w-full items-start no-wrap gap-3"):
                ui.avatar(icon=component_file_icon(component.get("mime_type")), color="blue-1", text_color="primary").props("rounded")
                with ui.column().classes("gap-1 grow min-w-0"):
                    ui.label(component.get("file_name") or "Unnamed file").classes("component-filename font-semibold text-slate-800")
                    ui.label(component.get("mime_type") or "Unknown file type").classes("text-xs text-slate-500")
                with ui.column().classes("items-end gap-1"):
                    ui.badge(f"#{component.get('component_order', '—')}").props("outline color=primary")
                    with ui.row().classes("gap-0 no-wrap"):
                        if on_view is not None:
                            ui.button(icon="visibility", on_click=lambda _, item=component: on_view(item)).props(
                                "flat round dense" + (" disable" if status != "available" or not capability_allowed(capabilities, "view_component") else "")
                            ).tooltip("View document" if capability_allowed(capabilities, "view_component") else "Your effective roles do not grant component viewing")
                        if on_download is not None:
                            ui.button(icon="download", on_click=lambda _, item=component: on_download(item)).props(
                                "flat round dense" + (" disable" if status != "available" or not capability_allowed(capabilities, "download_component") else "")
                            ).tooltip("Download original" if capability_allowed(capabilities, "download_component") else "Your effective roles do not grant component downloading")
                        ui.button(icon="arrow_upward", on_click=lambda _, item=component: on_move(item, -1)).props(
                            "flat round dense" + (" disable" if readonly or not capability_allowed(capabilities, "reorder_components") or index == 0 else "")
                        ).tooltip("Move earlier")
                        ui.button(icon="arrow_downward", on_click=lambda _, item=component: on_move(item, 1)).props(
                            "flat round dense" + (" disable" if readonly or not capability_allowed(capabilities, "reorder_components") or index == len(rows) - 1 else "")
                        ).tooltip("Move later")
                        ui.button(icon="delete_outline", color="negative", on_click=lambda _, item=component: on_remove(item)).props(
                            "flat round dense" + (" disable" if readonly or not capability_allowed(capabilities, "remove_component") else "")
                        ).tooltip("Remove component" if not readonly and capability_allowed(capabilities, "remove_component") else "This operation is unavailable under the current resource state or access policy")
                        if on_history is not None:
                            ui.button(icon="history", color="blue-grey", on_click=lambda _, item=component: on_history(item)).props("flat round dense").tooltip("Event history")
            with ui.row().classes("w-full items-center gap-2"):
                ui.badge(status.replace("_", " ").title(), color=status_color).props("rounded")
                ui.label(format_file_size(component.get("size_in_bytes"))).classes("text-sm font-medium text-slate-600")
            ui.separator()
            with ui.grid(columns=2).classes("w-full gap-x-6 gap-y-3"):
                for label, value in (
                    ("Originated", format_timestamp(component.get("date_originated"))),
                    ("Uploaded", format_timestamp(component.get("date_created"))),
                    ("Storage", str(component.get("storage_backend") or "—").title()),
                    (component.get("checksum_algo") or "Checksum", checksum_short),
                ):
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(label).classes("component-meta-label")
                        value_label = ui.label(value).classes("component-meta-value truncate max-w-full")
                        if value == checksum_short and checksum != "—":
                            value_label.tooltip(checksum)


def component_uploader(on_multi_upload, *, label: str = "Add digital components"):
    uploader = ui.upload(
        on_multi_upload=on_multi_upload,
        label=label,
        auto_upload=True,
        multiple=True,
    ).props("accept=*").classes("record-uploader w-full")
    uploader.add_slot("header", """
        <div class="row items-center no-wrap full-width q-pa-md q-gutter-md upload-header">
          <q-avatar icon="cloud_upload" color="blue-1" text-color="primary" size="42px" />
          <div class="column col">
            <span class="text-weight-medium text-slate-800">Add digital components</span>
            <span class="text-caption text-slate-500">Drag and drop files here, or choose them from your device</span>
          </div>
          <q-btn outline no-caps color="primary" icon="folder_open" label="Browse files">
            <q-uploader-add-trigger />
          </q-btn>
        </div>
    """)
    uploader.add_slot("list", """
        <div v-if="props.files.length === 0" class="upload-empty">
          Files can be dropped anywhere in this panel
        </div>
        <q-list v-else separator class="upload-queue">
          <q-item v-for="file in props.files" :key="file.__key" dense class="q-px-md q-py-sm">
            <q-item-section avatar style="min-width: 38px">
              <q-icon name="description" color="blue-grey-5" size="22px" />
            </q-item-section>
            <q-item-section class="min-width-0">
              <q-item-label class="text-weight-medium ellipsis">{{ file.name }}</q-item-label>
              <q-item-label caption>{{ file.__sizeLabel }} · {{ file.__progressLabel }}</q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-spinner v-if="file.__status === 'uploading'" color="primary" size="22px" />
              <q-icon v-else-if="file.__status === 'uploaded'" name="check_circle" color="positive" size="22px" />
              <q-icon v-else-if="file.__status === 'failed'" name="error" color="negative" size="22px" />
              <q-icon v-else name="schedule" color="blue-grey-4" size="22px" />
            </q-item-section>
          </q-item>
        </q-list>
    """)
    return uploader


def add_timestamp_slots(table: Any, column_names: list[str]) -> None:
    for key in column_names:
        table.add_slot(f"body-cell-{key}", """
            <q-td :props="props">
              <div v-if="props.value" class="row items-center no-wrap q-gutter-sm timestamp-cell">
                <q-icon name="schedule" color="blue-grey-4" size="18px" />
                <div class="column no-wrap">
                  <span class="timestamp-date">{{ new Date(props.value).toLocaleDateString(undefined, {day: 'numeric', month: 'short', year: 'numeric'}) }}</span>
                  <span class="timestamp-time">{{ new Date(props.value).toLocaleTimeString(undefined, {hour: 'numeric', minute: '2-digit'}) }}</span>
                </div>
                <q-tooltip>{{ props.value }}</q-tooltip>
              </div>
              <span v-else class="text-grey-5">—</span>
            </q-td>
        """)


def error_message(error: ApiError) -> str:
    if error.status_code == 412:
        return "This item changed after you opened it. Reload it before saving again."
    if error.status_code == 428:
        return "The item version is missing. Reload it and try again."
    if isinstance(error.detail, dict):
        messages = {
            "insufficient_privilege": "You do not have the required system privilege for this action.",
            "insufficient_resource_permission": "Your roles do not grant this action on the selected item.",
            "insufficient_clearance": "Your active roles do not have sufficient security clearance.",
        }
        if error.detail.get("code") in messages:
            return messages[error.detail["code"]]
    return error.message


def relationship_options(
    rows: list[dict[str, Any]], label_fields: tuple[str, ...]
) -> dict[int, str]:
    options: dict[int, str] = {}
    for item in rows:
        values = [str(item.get(name) or "").strip() for name in label_fields]
        values = [value for value in values if value]
        code = values[0] if len(values) > 1 else ""
        name = values[-1] if values else f"Item {item['id']}"
        options[item["id"]] = (
            f"{code} · {name}"
            if code else name
        )
    return options


def apply_relationship_selection(control: Any, value: int, label: str) -> None:
    """Atomically add a browsed relationship option and select it."""
    options = dict(control.options or {})
    options[int(value)] = label
    control.set_options(options, value=int(value))


def relationship_cell(item: dict[str, Any] | None, *, number_field: str | None = None) -> dict[str, Any] | None:
    if item is None:
        return None
    code = item.get("code") or (item.get(number_field) if number_field else None)
    return {
        "name": item.get("name") or item.get("title") or f"Item {item['id']}",
        "code": code,
    }


def decorate_relationship_rows(
    resource: str,
    rows: list[dict[str, Any]],
    related_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    related_by_id = {item["id"]: item for item in (related_rows or rows)}
    decorated = []
    for row in rows:
        item = dict(row)
        if resource == "org-units":
            item["parent_org_unit_display"] = relationship_cell(
                related_by_id.get(row.get("parent_org_unit_id"))
            )
        elif resource == "roles":
            item["org_unit_display"] = relationship_cell(
                related_by_id.get(row.get("org_unit_id"))
            )
        elif resource == "records":
            item["aggregation_display"] = relationship_cell(
                related_by_id.get(row.get("aggregation_id")),
                number_field="aggregation_number",
            )
        decorated.append(item)
    return decorated


def relationship_select(
    label: str,
    options: dict[int, str],
    *,
    value: Any = None,
    required: bool = False,
):
    lowered_label = label.lower()
    icon = (
        "folder" if "aggregation" in lowered_label
        else "corporate_fare" if "organization" in lowered_label or "unit" in lowered_label
        else "badge" if "role" in lowered_label
        else "person" if "user" in lowered_label
        else "link"
    )
    control = ui.select(
        options,
        label=label,
        value=value,
        with_input=True,
        clearable=not required,
    ).props(
        "outlined use-input input-debounce=0 behavior=menu options-dense"
    ).classes("w-full relationship-select")
    control.add_slot("prepend", f'<q-avatar size="34px" color="blue-1" text-color="primary" icon="{icon}" />')
    option_template = """
        <q-item v-bind="props.itemProps" class="relationship-option q-py-sm">
          <q-item-section avatar>
            <q-avatar color="blue-1" text-color="primary" icon="__ICON__" size="36px" />
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-medium">{{ props.opt.label.includes(' · ') ? props.opt.label.split(' · ').slice(1).join(' · ') : props.opt.label }}</q-item-label>
            <q-item-label caption class="row items-center q-gutter-xs">
              <q-badge v-if="props.opt.label.includes(' · ')" outline color="primary" :label="props.opt.label.split(' · ')[0]" />
            </q-item-label>
          </q-item-section>
          <q-item-section side><q-icon name="chevron_right" color="grey-5" /></q-item-section>
        </q-item>
    """.replace("__ICON__", icon)
    control.add_slot("option", option_template)
    return control


def field_input(field: FieldSpec, value: Any = None, options: dict[int, str] | None = None):
    display_label = f"{field.label} *" if field.required else field.label
    if field.kind == "account_type":
        return ui.select(
            {"person": "Person", "service": "Service"},
            label=display_label, value=value or "person",
        ).props("outlined").classes("w-full")
    if field.kind == "classification_type":
        return ui.select(
            {False: "Branch — may contain children", True: "Terminal — assignable to root aggregations"},
            label=display_label, value=False if value is None else value,
        ).props("outlined").classes("w-full")
    if field.kind == "disposition":
        return ui.select({
            "destruction": "Destruction",
            "transfer_to_external_archive": "Permanent preservation — external archive",
            "selective_preservation": "Selective preservation",
            "retain_as_local_archives": "Retain as local archives",
        }, label=display_label, value=value, clearable=True).props("outlined").classes("w-full")
    if field.kind == "textarea":
        return ui.textarea(display_label, value=value or "").props("outlined autogrow").classes("w-full")
    if field.kind == "int":
        return ui.number(display_label, value=value, format="%.0f").props("outlined").classes("w-full")
    if field.kind == "bool":
        return ui.checkbox(display_label, value=bool(value))
    if field.kind in {"lookup", "classification"}:
        return relationship_select(
            display_label, options or {}, value=value, required=field.required
        )
    if field.kind == "datetime":
        rendered = str(value or "")[:16]
        return ui.input(display_label, value=rendered).props("outlined type=datetime-local").classes("w-full")
    return ui.input(display_label, value=value or "").props("outlined").classes("w-full")


def form_payload(spec: EntitySpec, controls: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in spec.fields:
        value = controls[field.name].value
        if field.kind in {"int", "lookup", "classification"} and value not in (None, ""):
            value = int(value)
        if field.kind == "datetime" and value:
            value = datetime.fromisoformat(value).isoformat()
        if isinstance(value, str):
            value = value.strip()
        if field.required and value in (None, ""):
            raise ValueError(f"{field.label} is required")
        if creating and value in (None, "") and not field.required:
            continue
        payload[field.name] = None if value == "" else value
    return payload


@ui.page("/")
def index() -> None:
    # A client per page prevents one browser's token leaking into another and
    # keeps it available when dashboard calls run in child asyncio tasks.
    api = ErmsApiClient(api_url())
    page_client = context.client
    page_client.on_disconnect(api.close)
    auth_state: dict[str, Any] = {"principal": None}
    state: dict[str, Any] = {
        "resource": "dashboard", "rows": [], "searched": False,
        "recent_created": [], "recent_updated": [], "aggregation_detail": None,
        "lifecycle_filter": "all", "aggregation_mode": "search",
        "favourites": {"aggregations": [], "records": []},
        "favourite_ids": {"aggregations": set(), "records": set()},
    }
    stored_navigation = app.storage.user.get("navigation_trail")
    navigation_state: dict[str, Any] = {
        "trail": [
            item for item in (stored_navigation if isinstance(stored_navigation, list) else [])
            if isinstance(item, dict) and isinstance(item.get("page"), str)
        ][-NAVIGATION_TRAIL_LIMIT:],
        "restoring": False,
    }

    ui.colors(
        primary="#268bd2", secondary="#0f749f", accent="#72b8e8",
        positive="#2f9e44", warning="#e9a23b", negative="#dc5050",
    )

    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Righteous&display=swap" rel="stylesheet">'
        '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:'
        'opsz,wght,FILL,GRAD@20,300,0,0&display=swap" rel="stylesheet">'
    )
    ui.add_css("""
        :root {
            --erms-ink: #172033; --erms-muted: #687386; --erms-blue: #268bd2;
            --erms-blue-deep: #176da8; --erms-blue-soft: #eaf5fc;
            --erms-bg: #ffffff; --erms-surface: #fff; --erms-border: #e1e6eb;
        }
        body {
            background: var(--erms-bg); color: var(--erms-ink);
            font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
                         "Segoe UI", sans-serif;
            letter-spacing: -.008em;
        }
        /* Connection state is presented in the application footer. Keep
           NiceGUI's reconnect machinery, but suppress its duplicate popup. */
        #popup { display: none !important; }
        .erms-header {
            position: fixed; overflow: hidden;
            background: #f4f6f8; color: var(--erms-ink);
            border-bottom: 1px solid var(--erms-border); box-shadow: none !important;
            min-height: 54px; padding: 0 18px;
        }
        .wathiq-header-network {
            position: absolute; z-index: 0; inset: 0; width: 100%; height: 100%;
            pointer-events: none; background: transparent;
        }
        .erms-header > :not(.wathiq-header-network) { position: relative; z-index: 1; }
        .erms-footer {
            min-height: 34px; padding: 0 18px;
            background: #f4f6f8; color: #687386;
            border-top: 1px solid var(--erms-border); box-shadow: none !important;
        }
        .erms-footer-credit { font-size: .72rem; letter-spacing: .01em; }
        .erms-dashboard-card .erms-shared-control { display: none !important; }
        .erms-shared-control:empty { display: none !important; }
        .erms-brand { gap: 8px; min-width: 0; }
        .erms-brand-mark { width: 28px; height: 33px; flex: 0 0 auto; }
        .erms-brand-name {
            color: #152033; font-family: Righteous, Inter, ui-sans-serif, sans-serif;
            font-size: 1.24rem; font-weight: 400; letter-spacing: .035em; line-height: 1;
        }
        .erms-drawer {
            background: #ffffff; color: #172033;
            border-right: 1px solid var(--erms-border) !important;
            overflow: visible !important;
        }
        .erms-drawer .q-drawer__content { overflow-x: visible !important; }
        .erms-nav-scroll {
            height: 100%; overflow-y: auto; overflow-x: hidden;
            padding: 0 8px 24px; scrollbar-gutter: stable;
            overscroll-behavior: contain;
        }
        .erms-drawer-toggle {
            position: absolute !important; right: -13px; top: 18px; z-index: 20;
            width: 27px; height: 34px; min-width: 27px; min-height: 34px;
            padding: 0; border: 1px solid var(--erms-border);
            border-radius: 9px; background: #ffffff !important; color: #52657a !important;
        }
        .erms-drawer-toggle:hover {
            background: var(--erms-blue-soft) !important; color: var(--erms-blue-deep) !important;
        }
        .erms-drawer-toggle .q-icon,
        .erms-profile-action .q-icon {
            font-family: "Material Symbols Outlined" !important;
            font-weight: 300 !important;
            font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 20;
        }
        .erms-drawer-toggle .q-icon { font-size: 19px; }
        .erms-profile-action .q-icon { font-size: 21px; }
        .erms-profile-action .q-btn__content { gap: 12px; }
        .erms-profile-action {
            min-height: 38px !important; height: 38px !important;
            margin: 0 !important; padding: 2px 10px !important;
        }
        .erms-profile-actions {
            display: flex !important; flex-direction: column; gap: 0 !important;
            margin: 0 !important; padding: 0 !important;
        }
        .wathiq-login-card {
            position: relative; z-index: 2;
            width: min(680px, calc(100vw - 32px)); max-width: none !important;
            padding: 0 !important; gap: 0 !important; overflow: hidden;
            border: 1px solid var(--erms-border); border-radius: 18px;
        }
        .wathiq-login-network {
            position: fixed; z-index: 1; inset: 0; width: 100vw; height: 100vh;
            pointer-events: none;
            background:
                linear-gradient(135deg, rgba(245, 249, 251, .50), rgba(219, 237, 247, .22)),
                #eaf2f6;
        }
        .wathiq-login-brand-panel {
            width: 270px; min-height: 430px; padding: 34px;
            background: linear-gradient(145deg, #eaf5fc, #f7fbfe);
            border-right: 1px solid #d9eaf4;
        }
        .wathiq-login-mark { width: 35px; height: 42px; }
        .wathiq-login-word {
            color: #152033; font-family: Righteous, Inter, ui-sans-serif, sans-serif;
            font-size: 1.45rem; letter-spacing: .035em;
        }
        .wathiq-login-form { width: 410px; min-height: 430px; padding: 38px; }
        .wathiq-login-error { min-height: 20px; }
        @media (max-width: 640px) {
            .wathiq-login-brand-panel { display: none !important; }
            .wathiq-login-form { width: 100%; min-height: auto; padding: 30px 24px; }
        }
        .erms-nav-heading {
            color: var(--erms-blue-deep); font-size: .67rem; font-weight: 700;
            letter-spacing: .12em; text-transform: uppercase;
        }
        .erms-nav-link { position: relative; border-radius: 8px; color: #1f2937 !important; }
        .erms-nav-link .q-btn__content {
            width: 100%; gap: 12px; flex-wrap: nowrap; justify-content: flex-start;
        }
        .erms-nav-link .q-icon {
            font-family: "Material Symbols Outlined" !important;
            font-size: 21px; font-weight: 300 !important;
            font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 20;
        }
        .erms-nav-link .q-btn__content .block {
            min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .erms-nav-link:hover { background: var(--erms-blue-soft) !important; color: var(--erms-blue-deep); }
        .erms-nav-link--active {
            background: #fff4d7 !important; color: #174b72 !important;
        }
        .erms-nav-link--active::before {
            content: ""; position: absolute; left: -8px; top: 50%; transform: translateY(-50%);
            width: 4px; height: 24px; border-radius: 0 4px 4px 0; background: var(--erms-blue);
        }
        .erms-drawer--collapsed .erms-nav-link .q-btn__content {
            justify-content: center;
        }
        .erms-drawer--collapsed .erms-nav-link--active::before { left: 0; }
        .erms-page-title-icon {
            color: var(--erms-blue-deep);
            font-family: "Material Symbols Outlined" !important;
            font-size: 27px; font-weight: 300 !important;
            font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 24;
        }
        .erms-content { max-width: 1540px; margin: 0 auto; }
        .erms-card {
            background: var(--erms-surface); border: 1px solid var(--erms-border);
            border-radius: 14px; box-shadow: none;
        }
        .governance-overview-grid {
            display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr);
            width: 100%; gap: 14px; align-items: start;
        }
        .governance-purpose-card,
        .governance-status-card {
            width: 100%; min-height: 0; padding: 18px 20px;
            border: 1px solid var(--erms-border); border-radius: 14px;
        }
        .governance-purpose-card { background: #ffffff; }
        .governance-purpose-icon,
        .governance-metric-icon {
            display: flex; align-items: center; justify-content: center;
            flex: 0 0 auto; color: var(--erms-blue); background: var(--erms-blue-soft);
            border-radius: 10px;
        }
        .governance-purpose-icon { width: 38px; height: 38px; }
        .governance-requirements-grid {
            display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
            width: 100%; gap: 7px 18px; margin-top: 8px;
        }
        .governance-status-card { color: #3f4b5d; }
        .governance-status-critical { background: #fff4f2; border-color: #f1c7c1; color: #8f312d; }
        .governance-status-warning { background: #fff9e9; border-color: #efd99b; color: #765718; }
        .governance-status-healthy { background: #f0faf4; border-color: #bce1c9; color: #23633a; }
        .governance-status-icon {
            display: flex; align-items: center; justify-content: center;
            width: 32px; height: 32px; flex: 0 0 32px; border-radius: 999px;
            color: currentColor; background: rgba(255, 255, 255, .7);
        }
        .governance-metrics-row { width: 100%; gap: 10px; flex-wrap: wrap; }
        .governance-metric-card {
            width: 205px; min-height: 72px; padding: 12px 14px;
            display: flex !important; flex-direction: row !important;
            align-items: center; gap: 12px; border: 1px solid var(--erms-border);
            background: #ffffff; border-radius: 12px;
        }
        .governance-metric-icon { width: 32px; height: 32px; }
        .governance-empty-state {
            width: 100%; min-height: 126px; padding: 18px;
            align-items: center; justify-content: center; gap: 6px;
            border: 1px dashed #ccd8e4; background: #fbfcfd; border-radius: 12px;
        }
        .governance-empty-inline {
            width: 100%; padding: 18px; text-align: center; color: #718096;
            border: 1px dashed #ccd8e4; background: #fbfcfd; border-radius: 12px;
            font-size: .8rem;
        }
        .governance-table .q-table thead tr { background: #eef7fd; }
        .governance-table .q-table th { color: #35546f; text-align: left; }
        .governance-table .q-table td { text-align: left; }
        .governance-table .q-table th:last-child,
        .governance-table .q-table td:last-child { text-align: right; white-space: nowrap; }
        .security-operations-table .q-table th:last-child,
        .security-operations-table .q-table td:last-child { text-align: left; white-space: normal; }
        .login-sessions-table .q-table th {
            vertical-align: middle;
            white-space: nowrap;
        }
        .login-sessions-table .q-table th > * {
            flex-wrap: nowrap;
        }
        .login-sessions-table .q-table__sort-icon {
            flex: 0 0 auto;
        }
        .erms-profiles-table .q-table { table-layout: fixed; width: 100%; }
        .erms-profiles-table .q-table th,
        .erms-profiles-table .q-table td { overflow: hidden; }
        .erms-profiles-table .profile-description-cell {
            white-space: normal; overflow-wrap: anywhere; line-height: 1.35;
        }
        @media (max-width: 900px) {
            .governance-overview-grid { grid-template-columns: 1fr; }
            .governance-purpose-card, .governance-status-card { min-height: auto; }
        }
        @media (max-width: 560px) {
            .governance-requirements-grid { grid-template-columns: 1fr; }
            .governance-metric-card { width: 100%; }
        }
        .q-card { border-radius: 14px; }
        .erms-content .q-card { box-shadow: none !important; }
        .q-btn { border-radius: 9px; }
        .q-field--outlined .q-field__control { border-radius: 10px; }
        .q-table__container { border-radius: 12px; overflow: hidden; }
        .erms-page-table {
            width: calc(100% - 40px) !important;
            margin: 8px 20px 20px;
        }
        .erms-page-table .q-table thead tr { background: #eef7fd; }
        .erms-page-table .q-table th {
            color: #35546f; font-size: .74rem; font-weight: 700;
            letter-spacing: .045em;
        }
        .erms-page-table .q-table tbody td { color: #334155; font-size: .875rem; }
        .erms-page-table .q-table tbody tr:hover { background: #f7fbfe; }
        .erms-results-divider { width: calc(100% - 40px) !important; margin: 8px 20px 0; }
        .q-table thead tr { background: #f7f8f8; }
        .q-table th { color: #657184; font-size: .72rem; font-weight: 700; letter-spacing: .035em; }
        .detail-surface {
            background: var(--erms-surface); border: 1px solid var(--erms-border);
            border-radius: 14px;
        }
        .detail-field {
            min-width: 0; padding: 10px 0; border-bottom: 1px solid #eef0f2;
        }
        .detail-field-label {
            color: #8791a1; font-size: .67rem; font-weight: 700;
            letter-spacing: .065em; text-transform: uppercase;
        }
        .detail-field-value { color: #263244; font-size: .9rem; font-weight: 600; line-height: 1.4; }
        .retention-card {
            background: linear-gradient(135deg, #f5fbff 0%, #eaf5fc 100%);
            border: 1px solid #d5eaf8; border-radius: 14px;
        }
        .retention-line { position: relative; width: 22px; align-self: stretch; flex: 0 0 22px; }
        .retention-line::before {
            content: ""; position: absolute; top: 14px; bottom: -22px; left: 10px;
            width: 2px; background: #a9d6f3;
        }
        .retention-stage:last-child .retention-line::before { display: none; }
        .retention-dot {
            position: relative; z-index: 1; width: 11px; height: 11px; margin: 8px 0 0 5px;
            border-radius: 999px; background: var(--erms-blue); box-shadow: 0 0 0 4px #eaf5fc;
        }
        .retention-stage-label { color: #607086; font-size: .75rem; line-height: 1.2; }
        .retention-stage-value { color: #172033; font-size: 1.15rem; font-weight: 750; line-height: 1.25; }
        .relationship-select .q-field__control { min-height: 58px; border-radius: 10px; }
        .relationship-option { min-width: 360px; }
        .relationship-option:hover { background: #f3f7ff; }
        .relationship-select .q-field__native { font-weight: 600; color: #16324f; }
        .relationship-cell-name { color: #172033; }
        .recent-card { min-height: 62px; border: 1px solid #e2e8f0; border-radius: 10px; transition: all .16s ease; }
        .recent-card:hover { border-color: #93b4e8; background: #f8fcff; }
        .breadcrumb-link { color: #52657a; }
        .timestamp-date { font-size: .84rem; font-weight: 600; color: #334155; line-height: 1.15; }
        .timestamp-time { font-size: .72rem; color: #94a3b8; line-height: 1.2; }
        .component-grid { display: grid; grid-template-columns: 1fr; gap: 12px; padding-right: 8px; }
        .component-list { container-type: inline-size; overflow: visible; padding: 2px 0; }
        @container (min-width: 760px) { .component-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        .component-card { border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: none; overflow: hidden; }
        .component-card:hover { border-color: #a8bdd8; background: #fafdff; }
        .component-filename { overflow-wrap: anywhere; line-height: 1.25; }
        .component-meta-label { color: #94a3b8; font-size: .68rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; }
        .component-meta-value { color: #475569; font-size: .8rem; line-height: 1.3; }
        .record-uploader { border: 2px dashed #a9bfd9; border-radius: 12px; box-shadow: none; background: #fbfdff; }
        .record-uploader:hover { border-color: #5b8ec9; background: #f7fbff; }
        .record-uploader .q-uploader__header { background: transparent; color: inherit; }
        .record-uploader .q-uploader__list { min-height: 58px; padding: 0; }
        .upload-empty { display: flex; align-items: center; justify-content: center; min-height: 58px; color: #94a3b8; font-size: .78rem; }
        .upload-queue { max-height: 144px; overflow-y: auto; background: #f8fafc; }
        .membership-dialog {
            width: min(680px, calc(100vw - 32px)) !important;
            max-width: none !important;
            max-height: min(700px, calc(100vh - 32px));
            overflow: hidden;
        }
        .membership-table { height: min(330px, calc(100vh - 370px)); min-height: 250px; }
        .membership-table .q-table__middle { overflow-y: auto; }
        .membership-table thead tr th { position: sticky; top: 0; z-index: 1; background: white; }
        .audit-event { border-left: 3px solid #bfdbfe; box-shadow: none; }
        .audit-event:hover { border-left-color: #3b82f6; background: #f8fbff; }
        .audit-value { max-width: 360px; overflow-wrap: anywhere; white-space: pre-wrap; }
        .q-tooltip {
            max-width: min(360px, calc(100vw - 32px)) !important;
            white-space: normal !important;
            overflow-wrap: anywhere;
            line-height: 1.35;
            text-align: left;
        }
        .dashboard-stat { border: 1px solid #e2e8f0; box-shadow: none; transition: all .16s ease; }
        .dashboard-stat:hover { border-color: #93b4e8; background: #f8fcff; }
    """)

    with ui.header().classes("erms-header items-center gap-3"):
        header_network = ui.element("canvas").classes(
            "wathiq-network-canvas wathiq-header-network"
        ).props("aria-hidden=true")
        header_network.set_visibility(False)
        with ui.row().classes("erms-brand items-center no-wrap").props("aria-label='Wathiq'"):
            ui.image("/static/brand/wathiq-mark.svg?v=2").classes("erms-brand-mark").props(
                "fit=contain alt='Wathiq mark'"
            )
            ui.label("wathiq").classes("erms-brand-name")
        ui.space()
        user_menu_button = ui.button(icon="account_circle").props("flat round color=blue-grey-9")
        with user_menu_button, ui.menu() as user_menu:
            with ui.column().classes("w-72 p-3 gap-2"):
                with ui.row().classes("w-full items-center gap-3 no-wrap"):
                    with ui.avatar(size="44px").style(
                        "background:#64748b !important;color:white !important"
                    ) as current_user_avatar:
                        current_user_avatar_initials = ui.label("?").classes("font-medium")
                    with ui.column().classes("gap-0 min-w-0"):
                        current_user_name = ui.label("Not signed in").classes(
                            "font-semibold line-clamp-1"
                        )
                        current_user_email = ui.label().classes(
                            "text-xs text-slate-500 line-clamp-1"
                        )
                ui.separator()
                ui.label("Previous sign-in").classes("component-meta-label")
                current_user_last_login = ui.label("First sign-in").classes("text-sm text-slate-600")
                ui.separator()
                ui.label("Assigned roles").classes("component-meta-label")
                current_user_roles = ui.column().classes("w-full gap-1")
                ui.separator()
                with ui.column().classes("erms-profile-actions w-full").style(
                    "gap:0 !important;margin:0 !important;padding:0 !important"
                ):
                    change_password_menu = ui.button("Change password", icon="key").props(
                        "flat dense no-caps align=left"
                    ).classes("erms-profile-action w-full")
                    sign_out_menu = ui.button("Sign out", icon="logout", color="negative").props(
                        "flat dense no-caps align=left"
                    ).classes("erms-profile-action w-full")

    with ui.footer().classes("erms-footer items-center"):
        with ui.icon("cloud_done").classes("text-positive text-lg") as connection_icon:
            connection_tooltip = ui.tooltip("Connected")
        ui.space()
        ui.label("Designed and built by Sharjah Archives").classes("erms-footer-credit")

    def set_connection_status(connected: bool) -> None:
        connection_icon.name = "cloud_done" if connected else "cloud_off"
        connection_icon.classes(
            replace="text-positive text-lg" if connected else "text-negative text-lg"
        )
        connection_tooltip.text = "Connected" if connected else "Disconnected"
        connection_icon.update()
        connection_tooltip.update()

    drawer_links: list[tuple[Any, str, str]] = []
    drawer_headings: list[Any] = []
    drawer_sections: list[tuple[Any, tuple[str, ...]]] = []

    def drawer_link(
        label: str, icon: str, *, navigation_key: str, extra_classes: str = "",
    ) -> Any:
        button = ui.button(label, icon=icon).props(
            f'flat align=left no-caps aria-label="{label}"'
        ).classes(f"erms-nav-link w-full justify-start px-4 {extra_classes}")
        with button:
            ui.tooltip(label)
        drawer_links.append((button, label, navigation_key))
        return button

    with ui.left_drawer(value=True).props(
        "width=300 mini-width=64 show-if-above"
    ).classes("erms-drawer") as drawer:
        drawer_toggle_button = ui.button(icon="chevron_left").props(
            "flat dense aria-label='Collapse navigation'"
        ).classes("erms-drawer-toggle")
        with drawer_toggle_button:
            drawer_toggle_tooltip = ui.tooltip("Collapse navigation")
        navigation: dict[str, Any] = {}
        with ui.column().classes("erms-nav-scroll w-full gap-0 no-wrap"):
            dashboard_navigation = drawer_link(
                "Dashboard", "dashboard", navigation_key="dashboard", extra_classes="mt-4",
            )
            for heading, entries in (
                ("RECORDS MANAGEMENT", (("aggregations", "folder"), ("records", "description"), ("classification-schemes", "account_tree"))),
                ("ORGANIZATION STRUCTURE", (("org-units", "corporate_fare"), ("roles", "badge"), ("users", "group"))),
            ):
                heading_control = ui.label(heading).classes(
                    "erms-nav-heading px-4 pt-5 pb-2"
                )
                drawer_headings.append(heading_control)
                section_keys = tuple(key for key, _ in entries)
                if heading == "ORGANIZATION STRUCTURE":
                    organization_browser_navigation = drawer_link(
                        "Browse", "lan", navigation_key="organization-browser",
                    )
                    section_keys = ("organization-browser", *section_keys)
                drawer_sections.append((heading_control, section_keys))
                for key, icon in entries:
                    navigation[key] = drawer_link(
                        ENTITIES[key].label, icon, navigation_key=key,
                    )
            system_heading = ui.label("SYSTEM ADMINISTRATION").classes(
                "erms-nav-heading px-4 pt-5 pb-2"
            )
            drawer_headings.append(system_heading)
            drawer_sections.append((system_heading, (
                "audit-trail", "login-sessions", "security-operations",
                "security-levels", "profiles", "governance-custody",
            )))
            audit_navigation = drawer_link(
                "Audit trail", "manage_history", navigation_key="audit-trail",
            )
            sessions_navigation = drawer_link(
                "Login sessions", "devices", navigation_key="login-sessions",
            )
            security_operations_navigation = drawer_link(
                "Security operations", "monitor_heart", navigation_key="security-operations",
            )
            navigation["security-levels"] = drawer_link(
                "Security levels", "security", navigation_key="security-levels",
            )
            navigation["profiles"] = drawer_link(
                "Profiles", "admin_panel_settings", navigation_key="profiles",
            )
            custody_navigation = drawer_link(
                "Governance custody", "shield_person", navigation_key="governance-custody",
            )

    def set_active_drawer_link(page: str) -> None:
        navigation_key = {
            "aggregation-details": "aggregations",
            "record-details": "records",
            "classification-workspace": "classification-schemes",
            "org-unit-details": "org-units",
            "role-details": "roles",
            "user-details": "users",
        }.get(page, page)
        for button, _, key in drawer_links:
            if key == navigation_key:
                button.classes(add="erms-nav-link--active")
                button.props(add="aria-current=page")
            else:
                button.classes(remove="erms-nav-link--active")
                button.props(remove="aria-current")
            button.update()

    drawer_collapsed = False

    def refresh_drawer_visibility(privileges: set[str] | None = None) -> None:
        granted = privileges
        if granted is None:
            granted = set(
                (auth_state.get("principal") or {}).get("global_privileges", [])
            )
        link_visibility = {
            key: can_navigate(key, granted) for _, _, key in drawer_links
        }
        for button, _, key in drawer_links:
            button.set_visibility(link_visibility[key])
        for heading, section_keys in drawer_sections:
            heading.set_visibility(
                not drawer_collapsed
                and any(link_visibility.get(key, False) for key in section_keys)
            )

    def toggle_navigation_drawer() -> None:
        nonlocal drawer_collapsed
        drawer_collapsed = not drawer_collapsed
        if drawer_collapsed:
            drawer.props(add="mini")
            drawer.classes(add="erms-drawer--collapsed")
            drawer_toggle_button.props(
                remove="aria-label icon",
                add="aria-label='Expand navigation' icon=chevron_right",
            )
            drawer_toggle_tooltip.text = "Expand navigation"
            for heading in drawer_headings:
                heading.set_visibility(False)
            for button, _, _ in drawer_links:
                button.text = ""
                button.classes(add="justify-center px-0", remove="justify-start px-4")
                button.update()
        else:
            drawer.props(remove="mini")
            drawer.classes(remove="erms-drawer--collapsed")
            drawer_toggle_button.props(
                remove="aria-label icon",
                add="aria-label='Collapse navigation' icon=chevron_left",
            )
            drawer_toggle_tooltip.text = "Collapse navigation"
            for button, label, _ in drawer_links:
                button.text = label
                button.classes(add="justify-start px-4", remove="justify-center px-0")
                button.update()
            refresh_drawer_visibility()
        drawer.update()
        drawer_toggle_button.update()

    drawer_toggle_button.on("click", toggle_navigation_drawer)

    with ui.column().classes("erms-content w-full p-5 gap-4"):
        breadcrumb_host = ui.element("nav").props(
            "aria-label='Navigation history'"
        ).classes("w-full min-h-7")
        with ui.row().classes("w-full items-center no-wrap gap-4"):
            with ui.column().classes("gap-0 grow min-w-0"):
                with ui.row().classes("items-center no-wrap gap-2"):
                    page_title_icon = ui.icon("dashboard").classes("erms-page-title-icon")
                    title = ui.label().classes("text-2xl font-semibold")
                subtitle = ui.label().classes("text-sm text-slate-500")
            with ui.row().classes("items-center no-wrap gap-2 flex-none"):
                add_button = ui.button("Add", icon="add", color="primary").props("unelevated rounded")
                add_record_button = ui.button(
                    "Add record", icon="note_add", color="secondary"
                ).props("unelevated rounded")

        with ui.card().classes("erms-card w-full p-0") as content_card:
            with ui.row().classes(
                "erms-shared-control w-full items-center px-4 pt-4 gap-2"
            ) as aggregation_mode_bar:
                ui.label("View").classes("text-xs font-semibold uppercase tracking-wide text-slate-400 mr-1")
                aggregation_search_mode = ui.button("Search", icon="search").props(
                    "unelevated dense no-caps color=primary"
                )
                aggregation_browse_mode = ui.button(
                    "Browse classification", icon="account_tree"
                ).props("flat dense no-caps color=primary")
            with ui.row().classes(
                "erms-shared-control w-full items-end p-4 gap-2"
            ) as search_bar:
                search_input = ui.input("Search by number, title or description").props("outlined clearable").classes("grow")
                search_button = ui.button("Search", icon="search").props("unelevated")
            guidance = ui.label().classes(
                "erms-shared-control px-4 pb-4 text-slate-500"
            )
            table_container = ui.column().classes("w-full gap-0")
    content_card.set_visibility(False)
    aggregation_mode_bar.set_visibility(False)
    add_button.set_visibility(False)
    add_record_button.set_visibility(False)
    page_title_icon.set_visibility(False)

    def set_page_title_icon(page: str) -> None:
        icon_name = {
            "dashboard": "dashboard",
            "aggregations": "folder",
            "records": "description",
            "classification-schemes": "account_tree",
            "classification-workspace": "account_tree",
            "org-units": "corporate_fare",
            "roles": "badge",
            "users": "group",
            "organization-browser": "lan",
            "audit-trail": "manage_history",
            "login-sessions": "devices",
            "governance-custody": "shield_person",
            "security-operations": "monitor_heart",
        }.get(page)
        if icon_name:
            page_title_icon.name = icon_name
            page_title_icon.set_visibility(True)
            page_title_icon.update()
        else:
            page_title_icon.set_visibility(False)

    def current_navigation_snapshot() -> dict[str, Any]:
        return {
            "searched": bool(state.get("searched")),
            "search_text": str(search_input.value or ""),
            "lifecycle_filter": state.get("lifecycle_filter", "all"),
            "aggregation_mode": state.get("aggregation_mode", "search"),
        }

    def persist_navigation_trail() -> None:
        app.storage.user["navigation_trail"] = navigation_state["trail"]

    async def navigate_to_breadcrumb(index: int) -> None:
        trail = navigation_state["trail"]
        if index < 0 or index >= len(trail):
            return
        entry = dict(trail[index])
        navigation_state["trail"] = trail[:index + 1]
        persist_navigation_trail()
        navigation_state["restoring"] = True
        try:
            await restore_navigation_entry(entry)
        except ApiError as error:
            if error.status_code in {403, 404}:
                navigation_state["trail"] = navigation_state["trail"][:-1]
                persist_navigation_trail()
                ui.notify(
                    "That page is no longer available. Returning to the previous page.",
                    color="warning",
                )
                if navigation_state["trail"]:
                    await restore_navigation_entry(navigation_state["trail"][-1])
                else:
                    await select_dashboard()
            else:
                ui.notify(error_message(error), color="negative", close_button=True)
        finally:
            navigation_state["restoring"] = False
            render_navigation_breadcrumbs()

    def render_navigation_breadcrumbs() -> None:
        breadcrumb_host.clear()
        trail = navigation_state["trail"]
        breadcrumb_host.set_visibility(bool(auth_state.get("principal") and trail))
        if not trail or not auth_state.get("principal"):
            return
        visible, hidden = visible_navigation_indices(len(trail))
        with breadcrumb_host, ui.row().classes(
            "w-full items-center no-wrap gap-1 text-xs text-slate-500 overflow-hidden"
        ):
            previous_index = None
            for index in visible:
                if previous_index is not None and index > previous_index + 1:
                    with ui.button(icon="more_horiz").props(
                        f"flat round dense size=sm aria-label='{len(hidden)} hidden navigation entries'"
                    ):
                        with ui.menu():
                            for hidden_index in hidden:
                                item = trail[hidden_index]
                                ui.menu_item(
                                    item.get("label") or item["page"].replace("-", " ").title(),
                                    on_click=lambda _, target=hidden_index: navigate_to_breadcrumb(target),
                                )
                if previous_index is not None:
                    ui.icon("chevron_right", size="15px").props("aria-hidden=true").classes("shrink-0 text-slate-300")
                entry = trail[index]
                label = entry.get("label") or entry["page"].replace("-", " ").title()
                if index == len(trail) - 1:
                    ui.label(label).props("aria-current=page").classes(
                        "font-semibold text-slate-700 truncate max-w-64"
                    ).tooltip(entry.get("accessible_label") or label)
                else:
                    ui.button(
                        label, on_click=lambda _, target=index: navigate_to_breadcrumb(target),
                    ).props("flat dense no-caps color=blue-grey").classes(
                        "min-w-0 max-w-52 truncate px-1"
                    ).tooltip(entry.get("accessible_label") or label)
                previous_index = index

    def register_navigation(
        page: str, label: str, *, entity_id: int | None = None,
        accessible_label: str | None = None,
    ) -> None:
        if page == "dashboard":
            content_card.classes(add="erms-dashboard-card")
        else:
            content_card.classes(remove="erms-dashboard-card")
        set_active_drawer_link(page)
        set_page_title_icon(page)
        if navigation_state["restoring"]:
            return
        trail = navigation_state["trail"]
        if trail:
            trail[-1]["state"] = current_navigation_snapshot()
        entry = {
            "page": page,
            "label": label,
            "entity_id": entity_id,
            "accessible_label": accessible_label or label,
            "state": {},
        }
        navigation_state["trail"] = append_navigation_entry(trail, entry)
        persist_navigation_trail()
        render_navigation_breadcrumbs()

    async def breadcrumb_back(fallback: Any) -> None:
        if len(navigation_state["trail"]) > 1:
            await navigate_to_breadcrumb(len(navigation_state["trail"]) - 2)
            return
        result = fallback()
        if asyncio.iscoroutine(result):
            await result

    async def restore_navigation_entry(entry: dict[str, Any]) -> None:
        page = entry["page"]
        saved = entry.get("state") or {}
        entity_id = entry.get("entity_id")
        if page == "dashboard":
            await select_dashboard()
        elif page in ENTITIES:
            if page == "aggregations":
                state["aggregation_mode"] = saved.get("aggregation_mode", "search")
            await select_entity(page)
            search_input.value = saved.get("search_text", "")
            state["lifecycle_filter"] = saved.get("lifecycle_filter", "all")
            if saved.get("searched") and search_input.value and ENTITIES[page].search_first:
                await load_rows()
            elif state["lifecycle_filter"] != "all" and page in {"org-units", "roles", "users"}:
                render_table(ENTITIES[page])
        elif page == "classification-workspace":
            await select_classification_workspace()
        elif page == "organization-browser":
            await show_organization_structure()
        elif page == "audit-trail":
            await select_audit_trail()
        elif page == "login-sessions":
            await select_login_sessions()
        elif page == "governance-custody":
            await select_governance_custody()
        elif page == "security-operations":
            await select_security_operations()
        elif page == "aggregation-details" and entity_id is not None:
            await open_aggregation(await api.get("aggregations", entity_id))
        elif page == "record-details" and entity_id is not None:
            await select_record_details(entity_id)
        elif page == "org-unit-details" and entity_id is not None:
            await select_organization_unit_details(entity_id)
        elif page == "role-details" and entity_id is not None:
            await select_role_details(entity_id)
        elif page == "user-details" and entity_id is not None:
            await select_user_details(entity_id)
        else:
            raise ApiError(404, "Navigation target is no longer available")

    def clear_authenticated_view() -> None:
        """Remove protected data as soon as there is no authenticated principal."""
        state.update(resource="dashboard", rows=[], searched=False, aggregation_detail=None)
        state.pop("aggregation_browse", None)
        state["favourites"] = {"aggregations": [], "records": []}
        state["favourite_ids"] = {"aggregations": set(), "records": set()}
        title.text = ""
        subtitle.text = ""
        page_title_icon.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        content_card.set_visibility(False)
        breadcrumb_host.set_visibility(False)

    def clear_signed_in_identity() -> None:
        """Remove account identity and overlays before presenting sign-in again."""
        drawer.hide()
        user_menu.close()
        auth_state["principal"] = None
        current_user_name.text = "Not signed in"
        current_user_email.text = ""
        current_user_avatar_initials.text = "?"
        current_user_avatar.style(
            replace="background:#64748b !important;color:white !important"
        )
        current_user_last_login.text = "First sign-in"
        current_user_roles.clear()
        header_network.set_visibility(False)
        navigation_state["trail"] = []
        app.storage.user.pop("navigation_trail", None)
        clear_authenticated_view()

    def show_authenticated_view() -> None:
        content_card.set_visibility(True)

    async def reload_favourites() -> dict[str, list[dict[str, Any]]]:
        favourites = await api.favourites()
        state["favourites"] = favourites
        state["favourite_ids"] = {
            resource: {int(item["id"]) for item in favourites[resource]}
            for resource in ("aggregations", "records")
        }
        return favourites

    def favourite_state(resource: str, entity_id: int) -> bool:
        return int(entity_id) in state["favourite_ids"][resource]

    def apply_favourite_button(button: Any, tooltip: Any, selected: bool) -> None:
        label = "Remove from favourites" if selected else "Add to favourites"
        button.props(remove="icon color aria-label")
        button.props(
            f"icon={'favorite' if selected else 'favorite_border'} "
            f"color={'red' if selected else 'primary'} aria-label='{label}'"
        )
        tooltip.text = label
        button.update()
        tooltip.update()

    async def toggle_favourite(
        resource: str, entity_id: int, *, button: Any | None = None,
        tooltip: Any | None = None, on_changed: Any | None = None,
    ) -> bool:
        was_selected = favourite_state(resource, entity_id)
        now_selected = not was_selected
        if button is not None:
            button.disable()
            if tooltip is not None:
                apply_favourite_button(button, tooltip, now_selected)
        ids = state["favourite_ids"][resource]
        (ids.add if now_selected else ids.discard)(int(entity_id))
        try:
            if now_selected:
                await api.favourite(resource, entity_id)
            else:
                await api.unfavourite(resource, entity_id)
            ui.notify(
                "Added to favourites" if now_selected else "Removed from favourites",
                color="positive",
            )
            if on_changed is not None:
                result = on_changed(now_selected)
                if asyncio.iscoroutine(result):
                    await result
            return now_selected
        except ApiError as error:
            (ids.add if was_selected else ids.discard)(int(entity_id))
            if button is not None and tooltip is not None:
                apply_favourite_button(button, tooltip, was_selected)
            ui.notify(error_message(error), color="negative", close_button=True)
            return was_selected
        finally:
            if button is not None:
                button.enable()

    def favourite_button(resource: str, entity_id: int, *, on_changed: Any | None = None) -> Any:
        selected = favourite_state(resource, entity_id)
        button = ui.button(
            icon="favorite" if selected else "favorite_border",
        ).props(
            f"flat round dense color={'red' if selected else 'primary'} "
            f"aria-label='{'Remove from favourites' if selected else 'Add to favourites'}'"
        )
        with button:
            tooltip = ui.tooltip(
                "Remove from favourites" if selected else "Add to favourites"
            )
        button.on(
            "click",
            lambda: toggle_favourite(
                resource, entity_id, button=button, tooltip=tooltip,
                on_changed=on_changed,
            ),
            js_handler=STOP_PROPAGATION_CLICK_HANDLER,
        )
        return button

    entity_types = {
        "aggregations": "aggregation", "records": "record",
        "digital-components": "digital_component", "org-units": "org_unit",
        "users": "user", "roles": "role",
        "classification-schemes": "classification_scheme",
        "classifications": "classification",
    }

    def event_value(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def event_reference_value(event: dict[str, Any], side: str, field: str, value: Any) -> str:
        """Prefer the immutable readable identity captured with a new audit event."""
        references = (
            (event.get("metadata") or {})
            .get("reference_snapshots", {})
            .get(side, {})
        )
        snapshot = references.get(field) or {}
        if not snapshot:
            return event_value(value)
        primary = snapshot.get("code") or snapshot.get("name") or snapshot.get("title")
        secondary = snapshot.get("title") or snapshot.get("name") or snapshot.get("email")
        if secondary == primary:
            secondary = None
        identity = " — ".join(str(part) for part in (primary, secondary) if part)
        return identity or event_value(value)

    def event_entity_identity(event: dict[str, Any]) -> tuple[str, str]:
        entity_type = event["entity_type"]
        snapshot = event.get("after_state") or event.get("before_state") or {}
        current = event.get("_current_entity") or event.get("_historical_entity") or {}

        if entity_type == "user_role_assignment":
            parties = (event.get("metadata") or {}).get("assignment_parties") or {}
            assigned_user = parties.get("user") or {}
            assigned_role = parties.get("role") or {}
            user_identity = assigned_user.get("name") or "Unknown user"
            if assigned_user.get("email"):
                user_identity += f" ({assigned_user['email']})"
            role_identity = " — ".join(
                str(part) for part in (assigned_role.get("code"), assigned_role.get("name"))
                if part
            ) or "Unknown role"
            return "Role assignment", f"{user_identity} → {role_identity}"

        value = lambda field: snapshot.get(field) or current.get(field)
        identities = {
            "aggregation": (value("aggregation_number"), value("title")),
            "record": (value("record_number"), value("title")),
            "digital_component": (value("file_name"), None),
            "org_unit": (value("code"), value("name")),
            "user": (value("name"), value("email")),
            "role": (value("code"), value("name")),
            "classification_scheme": (value("code"), value("title")),
            "classification": (value("code"), value("title")),
        }
        primary, secondary = identities.get(entity_type, (None, None))
        identity = " — ".join(str(value) for value in (primary, secondary) if value)
        heading = f"{entity_type.replace('_', ' ').title()} #{event['entity_id']}"
        return heading, identity

    def hydrate_historical_audit_identities(events_list: list[dict[str, Any]]) -> None:
        """Reuse immutable snapshots within the result set without extra API calls."""
        identities: dict[tuple[str, int], dict[str, Any]] = {}
        for event in reversed(events_list):
            snapshot = event.get("after_state") or event.get("before_state")
            if snapshot:
                identities[(event["entity_type"], event["entity_id"])] = snapshot
        for event in events_list:
            event["_historical_entity"] = identities.get((event["entity_type"], event["entity_id"]))

    def event_actor_identity(event: dict[str, Any]) -> tuple[str, str | None]:
        if event.get("actor_name"):
            return event["actor_name"], event.get("actor_email") or "No email address"
        actor_type = event.get("actor_type") or "unknown"
        if event.get("actor_user_id"):
            return "User identity was not captured", None
        labels = {
            "anonymous": "Anonymous actor",
            "automated_process": "Automated process",
            "user": "Application user",
        }
        return labels.get(actor_type, actor_type.replace("_", " ").title()), None

    async def navigate_to_event_entity(event: dict[str, Any]) -> None:
        entity = event.get("_current_entity")
        if not entity:
            resources = {
                "aggregation": "aggregations", "record": "records",
                "digital_component": "digital-components", "org_unit": "org-units",
                "user": "users", "role": "roles",
                "classification_scheme": "classification-schemes",
                "classification": "classifications",
            }
            resource = resources.get(event["entity_type"])
            if not resource:
                ui.notify("This event type does not have a standalone entity page.", color="warning")
                return
            try:
                entity = await api.get(resource, event["entity_id"])
                event["_current_entity"] = entity
            except ApiError as error:
                if error.status_code == 404:
                    ui.notify("This entity no longer exists; its historical details remain in the audit event.", color="warning")
                else:
                    ui.notify(error_message(error), color="negative", close_button=True)
                return
        origin_dialog = event.get("_origin_dialog")
        if origin_dialog:
            origin_dialog.close()
            await asyncio.sleep(0.15)
        entity_type = event["entity_type"]
        if entity_type == "aggregation":
            await open_aggregation(entity)
        elif entity_type == "record":
            await show_record_details(entity)
        elif entity_type == "digital_component":
            try:
                record = await api.get("records", entity["record_id"])
                with table_container:
                    await show_components(record)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
        elif entity_type == "classification_scheme":
            await select_classification_workspace(initial_scheme_id=entity["id"])
        elif entity_type == "classification":
            await select_classification_workspace(
                initial_scheme_id=entity["classification_scheme_id"],
                initial_classification_id=entity["id"],
            )
        elif entity_type in {"org_unit", "user", "role"}:
            resource = {
                "org_unit": "org-units", "user": "users", "role": "roles",
            }[entity_type]
            await select_entity(resource)
            with table_container:
                await open_editor(entity)

    def show_event_detail(event: dict[str, Any]) -> None:
        entity_heading, entity_identity = event_entity_identity(event)
        dialog = ui.dialog()
        before = event.get("before_state") or {}
        after = event.get("after_state") or {}
        changed = event.get("changed_fields") or sorted(set(before) | set(after))
        actor_name, actor_email = event_actor_identity(event)

        async def open_entity() -> None:
            dialog.close()
            await asyncio.sleep(0.05)
            await navigate_to_event_entity(event)

        with dialog, ui.card().classes("p-0 max-h-[calc(100vh-32px)]").style("width: 960px; max-width: calc(100vw - 32px)"):
            with ui.row().classes("w-full items-center px-5 pt-5"):
                ui.avatar(icon="history", color="blue-1", text_color="primary")
                with ui.column().classes("gap-0 grow"):
                    ui.label(event["operation"].replace("_", " ").title()).classes("text-xl font-semibold")
                    ui.label(entity_heading).classes("text-sm text-slate-500")
                    if entity_identity:
                        ui.label(entity_identity).classes("text-sm font-medium text-slate-700 line-clamp-1")
                if event["entity_type"] in {"aggregation", "record", "digital_component", "org_unit", "user", "role"}:
                    ui.button(
                        "Open entity", icon="open_in_new",
                        on_click=open_entity,
                    ).props("flat no-caps color=primary")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
            with ui.column().classes("w-full px-5 pb-4 gap-4 overflow-y-auto"):
                with ui.row().classes("w-full gap-5 text-sm"):
                    with ui.column().classes("gap-0"):
                        ui.label("Occurred").classes("component-meta-label")
                        ui.label(format_timestamp(event.get("occurred_at"))).classes("text-sm text-slate-700")
                    with ui.column().classes("gap-0 min-w-[220px]"):
                        ui.label("Actor").classes("component-meta-label")
                        ui.label(actor_name).classes("text-sm font-medium text-slate-700")
                        if actor_email:
                            ui.label(actor_email).classes("text-xs text-slate-500")
                    with ui.column().classes("gap-0"):
                        ui.label("Source").classes("component-meta-label")
                        ui.label(event.get("source") or "—").classes("text-sm text-slate-700")
                if event.get("reason"):
                    with ui.card().classes("w-full bg-blue-50 shadow-none border border-blue-100"):
                        ui.label("Change reason").classes("component-meta-label")
                        ui.label(event["reason"]).classes("text-sm")
                if changed:
                    ui.label("Field changes").classes("font-semibold")
                    change_rows = [
                        {
                            "field": field.replace("_", " ").title(),
                            "before": event_reference_value(event, "before", field, before.get(field)),
                            "after": event_reference_value(event, "after", field, after.get(field)),
                        }
                        for field in changed
                    ]
                    change_table = ui.table(
                        columns=[
                            {"name": "field", "label": "Field", "field": "field", "align": "left"},
                            {"name": "before", "label": "Before", "field": "before", "align": "left"},
                            {"name": "after", "label": "After", "field": "after", "align": "left"},
                        ], rows=change_rows, row_key="field",
                    ).props("flat bordered wrap-cells hide-pagination").classes("w-full")
                    for key in ("before", "after"):
                        change_table.add_slot(f"body-cell-{key}", f'<q-td :props="props"><div class="audit-value">{{{{ props.row.{key} }}}}</div></q-td>')
                with ui.grid(columns=2).classes("w-full gap-3"):
                    for label, value in (
                        ("Request ID", event.get("request_id")),
                        ("Correlation ID", event.get("correlation_id")),
                        ("Transaction", event.get("transaction_id")),
                        ("Event ID", event.get("id")),
                    ):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(label).classes("component-meta-label")
                            ui.label(event_value(value)).classes("text-xs text-slate-600 break-all")
                if event.get("metadata"):
                    ui.label("Metadata").classes("font-semibold")
                    ui.code(json.dumps(event["metadata"], ensure_ascii=False, indent=2, sort_keys=True)).classes("w-full text-xs")
        dialog.open()

    def render_event_timeline(events_list: list[dict[str, Any]], container: Any) -> None:
        container.clear()
        with container:
            if not events_list:
                with ui.column().classes("w-full items-center py-10 text-slate-400 gap-2"):
                    ui.icon("history_toggle_off").classes("text-4xl")
                    ui.label("No matching events")
                return
            previous_correlation = None
            for event in events_list:
                actor_name, actor_email = event_actor_identity(event)
                correlation = event.get("correlation_id")
                if correlation and correlation != previous_correlation:
                    ui.label(f"Correlation group · {str(correlation)[:8]}").classes(
                        "text-xs text-slate-400 font-medium mt-2"
                    ).tooltip("Events sharing this correlation ID belong to the same request or coordinated operation")
                previous_correlation = correlation
                operation = event["operation"].replace("_", " ").title()
                entity_heading, entity_identity = event_entity_identity(event)
                with ui.card().classes("audit-event w-full px-4 py-3"):
                    with ui.row().classes("w-full items-center no-wrap gap-3"):
                        ui.avatar(icon={"CREATE": "add", "UPDATE": "edit", "DELETE": "delete"}.get(event["operation"], "bolt"), color="blue-1", text_color="primary", size="36px")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(operation).classes("font-semibold")
                            ui.label(entity_heading).classes("text-xs text-slate-500")
                            if entity_identity:
                                ui.label(entity_identity).classes("text-sm font-medium text-slate-700 line-clamp-1")
                            if event.get("changed_fields"):
                                ui.label(", ".join(field.replace("_", " ") for field in event["changed_fields"])).classes("text-xs text-slate-400 line-clamp-1")
                        with ui.column().classes("items-end gap-0"):
                            ui.label(format_timestamp(event["occurred_at"])).classes("text-xs font-medium text-slate-600")
                            ui.label(actor_name).classes("text-xs font-medium text-slate-600")
                            if actor_email:
                                ui.label(actor_email).classes("text-xs text-slate-400")
                            ui.label(event.get("source", "unknown")).classes("text-xs text-slate-400")
                        if event["entity_type"] in {"aggregation", "record", "digital_component", "org_unit", "user", "role"}:
                            ui.button(
                                icon="open_in_new",
                                on_click=lambda _, item=event: navigate_to_event_entity(item),
                            ).props("flat round dense color=primary").tooltip("Open current entity")
                        ui.button(
                            icon="chevron_right",
                            on_click=lambda _, item=event: show_event_detail(item),
                        ).props("flat round dense color=blue-grey").tooltip("View audit details")

    async def show_entity_history(resource: str, entity: dict[str, Any]) -> None:
        try:
            history = await api.history(resource, entity["id"])
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        name = entity.get("title") or entity.get("name") or entity.get("file_name") or f"#{entity['id']}"
        dialog = ui.dialog()
        for event in history:
            event["_current_entity"] = entity
            event["_origin_dialog"] = dialog
        with dialog, ui.card().classes("p-0 max-h-[calc(100vh-32px)]").style("width: 820px; max-width: calc(100vw - 32px)"):
            with ui.row().classes("w-full items-center px-5 py-4 border-b"):
                ui.avatar(icon="manage_history", color="blue-1", text_color="primary")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label("Event history").classes("text-xl font-semibold")
                    ui.label(name).classes("text-sm text-slate-500 line-clamp-1")
                ui.badge(str(len(history)), color="primary").props("outline")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
            timeline = ui.column().classes("w-full gap-2 px-5 pb-5 overflow-y-auto")
            render_event_timeline(history, timeline)
        dialog.open()

    async def show_components(record: dict[str, Any], *, container: Any | None = None) -> None:
        try:
            aggregations, component_capabilities = await asyncio.gather(
                api.list("aggregations"), api.resource_capabilities("records", record["id"]),
            )
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        aggregations_by_id = {item["id"]: item for item in aggregations}
        closure = effective_closure(
            aggregations_by_id.get(record.get("aggregation_id")), aggregations_by_id
        )
        readonly = closure is not None
        current_rows: list[dict[str, Any]] = []
        upload_lock = asyncio.Lock()
        uploader_control: dict[str, Any] = {}
        component_refresh: dict[str, Any] = {}

        async def download_component(component: dict[str, Any]) -> None:
            try:
                content = await api.download_component(component["id"])
                ui.download(content, component["file_name"], component.get("mime_type") or "application/octet-stream")
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def view_component(component: dict[str, Any]) -> None:
            converting = requires_document_conversion(component)
            progress_dialog = ui.dialog().props("persistent")
            with progress_dialog, ui.card().classes("w-[440px] max-w-full p-6"):
                with ui.row().classes("w-full items-center no-wrap gap-4"):
                    ui.spinner("dots", size="3em", color="primary")
                    with ui.column().classes("gap-1 grow min-w-0"):
                        ui.label("Preparing preview").classes("text-lg font-semibold")
                        ui.label(
                            "Converting this document to PDF. Larger files may take a little while."
                            if converting else
                            "Loading the document. Larger files may take a little while."
                        ).classes("text-sm text-slate-500")
                        ui.label(component.get("file_name") or "Document").classes(
                            "text-xs text-slate-400 truncate max-w-full"
                        )
                ui.linear_progress(show_value=False, color="primary").props(
                    "indeterminate"
                ).classes("w-full mt-3")
            progress_dialog.open()
            await asyncio.sleep(0)
            try:
                preview = await api.view_component_pdf(component["id"])
            except ApiError as error:
                progress_dialog.close()
                ui.notify(error_message(error), color="negative", close_button=True)
                return
            progress_dialog.close()
            preview_kind = native_preview_kind(component.get("mime_type"))
            if preview_kind:
                mime_type = component.get("mime_type") or "application/octet-stream"
                data_url = f"data:{mime_type};base64,{base64.b64encode(preview).decode('ascii')}"
                dialog = ui.dialog().props("maximized transition-show=fade transition-hide=fade")
                with dialog, ui.card().classes("w-full h-full p-0 gap-0 bg-slate-100"):
                    with ui.row().classes("w-full items-center no-wrap px-4 py-2 bg-white border-b"):
                        ui.icon(component_file_icon(mime_type), color="primary", size="28px")
                        ui.label(component["file_name"]).classes("font-semibold grow min-w-0 truncate")
                        ui.button(icon="download", on_click=lambda: download_component(component)).props("flat round dense").tooltip("Download original")
                        ui.button(icon="close", on_click=dialog.close).props("flat round dense").tooltip("Close viewer")
                    with ui.element("div").classes("w-full grow overflow-auto flex items-center justify-center p-6"):
                        if preview_kind == "image":
                            ui.image(data_url).classes("max-w-full max-h-[calc(100vh-100px)] object-contain shadow-lg")
                        elif preview_kind == "audio":
                            with ui.card().classes("w-[680px] max-w-full p-8"):
                                ui.icon("audio_file", size="72px").classes("self-center text-primary")
                                ui.label(component["file_name"]).classes("self-center font-semibold")
                                ui.audio(data_url, controls=True).classes("w-full")
                        else:
                            ui.video(data_url, controls=True).classes("w-full max-w-[1200px] max-h-[calc(100vh-110px)] bg-black")
                dialog.open()
                return
            canvas_id = f"erms-pdf-canvas-{component['id']}"
            dialog = ui.dialog().props("maximized transition-show=fade transition-hide=fade")

            def close_viewer() -> None:
                ui.run_javascript(f"window.ermsPdfViewer?.close({json.dumps(canvas_id)})")
                dialog.close()

            with dialog, ui.card().classes("w-full h-full p-0 gap-0 bg-slate-100"):
                with ui.row().classes("w-full items-center no-wrap px-4 py-2 bg-white border-b"):
                    ui.icon("picture_as_pdf", color="primary", size="28px")
                    ui.label(component["file_name"]).classes("font-semibold grow min-w-0 truncate")
                    ui.button(icon="chevron_left", on_click=lambda: ui.run_javascript(
                        f"window.ermsPdfViewer.previous({json.dumps(canvas_id)})"
                    )).props("flat round dense").tooltip("Previous page")
                    ui.label("Loading…").props(f'id={canvas_id}-status').classes("text-sm text-slate-500 min-w-32 text-center")
                    ui.button(icon="chevron_right", on_click=lambda: ui.run_javascript(
                        f"window.ermsPdfViewer.next({json.dumps(canvas_id)})"
                    )).props("flat round dense").tooltip("Next page")
                    ui.button(icon="zoom_out", on_click=lambda: ui.run_javascript(
                        f"window.ermsPdfViewer.zoomOut({json.dumps(canvas_id)})"
                    )).props("flat round dense").tooltip("Zoom out")
                    ui.button(icon="zoom_in", on_click=lambda: ui.run_javascript(
                        f"window.ermsPdfViewer.zoomIn({json.dumps(canvas_id)})"
                    )).props("flat round dense").tooltip("Zoom in")
                    ui.button(icon="download", on_click=lambda: download_component(component)).props("flat round dense").tooltip("Download original")
                    ui.button(icon="close", on_click=close_viewer).props("flat round dense").tooltip("Close viewer")
                with ui.element("div").classes("w-full grow overflow-auto flex justify-center items-start p-5"):
                    ui.element("canvas").props(f"id={canvas_id}").classes("bg-white shadow-lg")
            dialog.open()
            encoded = base64.b64encode(preview).decode("ascii")
            try:
                await ui.run_javascript(
                    "import('/static/pdfjs/erms-viewer.mjs').then(() => true)", timeout=15,
                )
                await ui.run_javascript(
                    f"window.ermsPdfViewer.open({json.dumps(canvas_id)}, {json.dumps(encoded)})",
                    timeout=30,
                )
            except TimeoutError:
                ui.notify("The PDF viewer did not finish loading", color="negative")

        def uploaded(event: events.MultiUploadEventArguments) -> None:
            try:
                buffered_files = buffer_upload_batch(event)
            except (OSError, ValueError) as error:
                ui.notify(f"Could not read an uploaded file: {error}", color="negative", close_button=True)
                return

            async def stage_buffered_files() -> None:
                try:
                    async with upload_lock:
                        await component_refresh["fn"]()
                        first_position = len(current_rows) + 1
                        for offset, (content, name, mime_type) in enumerate(buffered_files):
                            await api.upload_component(
                                record["id"], first_position + offset, name, content, mime_type,
                            )
                            await component_refresh["fn"]()
                    with component_area:
                        ui.notify(
                            f"{len(buffered_files)} digital component{'s' if len(buffered_files) != 1 else ''} uploaded",
                            color="positive",
                        )
                    uploader_control["uploader"].reset()
                except ApiError as error:
                    with component_area:
                        ui.notify(error_message(error), color="negative", close_button=True)

            background_tasks.create(
                stage_buffered_files(), name=f"stage components for record {record['id']}"
            )

        dialog = None
        component_area: Any = None

        def render_current_components() -> None:
            component_area.clear()
            with component_area:
                if not current_rows:
                    with ui.column().classes(
                        "col-span-full w-full items-center justify-center py-10 gap-2 text-center text-slate-400"
                    ):
                        ui.icon("cloud_upload").classes("text-4xl")
                        ui.label("No digital components have been uploaded yet.")
                else:
                    render_component_cards(
                        current_rows, move_component, remove_component,
                        lambda item: show_entity_history("digital-components", item),
                        view_component, download_component, readonly=readonly,
                        capabilities=component_capabilities,
                    )

        async def refresh_components() -> None:
            try:
                rows = await api.components(record["id"])
                current_rows.clear()
                current_rows.extend(rows)
                render_current_components()
            except ApiError as error:
                ui.notify(error_message(error), color="negative")

        async def move_component(component: dict[str, Any], direction: int) -> None:
            index = next((i for i, item in enumerate(current_rows) if item["id"] == component["id"]), -1)
            target = index + direction
            if index < 0 or target < 0 or target >= len(current_rows):
                return
            reordered = list(current_rows)
            reordered[index], reordered[target] = reordered[target], reordered[index]
            try:
                await api.reorder_components(record["id"], [
                    {"id": item["id"], "component_order": position}
                    for position, item in enumerate(reordered, 1)
                ])
                await refresh_components()
            except ApiError as error:
                ui.notify(error_message(error), color="negative")

        async def remove_component(component: dict[str, Any]) -> None:
            previous_rows = list(current_rows)
            current_rows[:] = [item for item in current_rows if item["id"] != component["id"]]
            render_current_components()
            try:
                await api.delete_component(component["id"], component["version"])
                ui.notify("Digital component removed", color="positive")
                await refresh_components()
            except ApiError as error:
                current_rows[:] = previous_rows
                render_current_components()
                ui.notify(error_message(error), color="negative")

        component_refresh["fn"] = refresh_components

        async def render_component_section(*, standalone: bool) -> None:
            nonlocal component_area
            if standalone:
                with ui.row().classes("w-full items-start no-wrap"):
                    with ui.column().classes("gap-0 grow"):
                        ui.label("Digital components").classes("text-xl font-semibold")
                        ui.label(f"Record {record['record_number']}").classes("text-sm text-slate-500")
                    ui.button(icon="close", on_click=dialog.close).props("flat round dense")
            scroll_classes = (
                "w-full overflow-y-auto max-h-[calc(100vh-190px)] pr-1"
                if standalone else "w-full"
            )
            with ui.element("div").classes(scroll_classes):
                if readonly:
                    with ui.row().classes("w-full items-start gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg"):
                        ui.icon("lock", color="amber-8")
                        with ui.column().classes("gap-0 grow"):
                            ui.label("Digital components are read-only").classes("font-semibold text-amber-900")
                            ui.label(
                                f"Closed by {closure['aggregation_number']} — {closure['title']}. "
                                "Files may still be viewed or downloaded."
                            ).classes("text-sm text-amber-800")
                elif component_capabilities.get("add_component"):
                    uploader_control["uploader"] = component_uploader(uploaded)
                else:
                    with ui.row().classes("w-full items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3"):
                        ui.icon("lock", color="blue-grey")
                        ui.label("Adding digital components is unavailable under your effective privileges, clearance, and resource ACL.").classes("text-sm text-slate-600")
                with ui.element("div").classes("component-list w-full mt-3"):
                    component_area = ui.element("div").classes("component-grid w-full")

            if standalone:
                with ui.row().classes("w-full justify-end"):
                    ui.button("Close", on_click=dialog.close).props("flat")
            await refresh_components()

        if container is None:
            dialog = ui.dialog()
            with dialog, ui.card().classes("max-h-[calc(100vh-32px)]").style("width: 920px; max-width: calc(100vw - 32px)"):
                await render_component_section(standalone=True)
        else:
            with container:
                await render_component_section(standalone=False)
        if dialog is not None:
            dialog.open()

    async def show_acl_editor(
        resource: str, entity_id: int, *, scope: str = "resource",
        on_saved: Callable[[], Any] | None = None,
    ) -> None:
        """Edit a complete ACL atomically; inherited and dormant sets stay visually distinct."""
        resource_type = "record" if resource == "records" or scope == "record" else "aggregation"
        try:
            catalogue = await api.permissions_catalogue(resource_type)
            roles = await api.list("roles", limit=500)
            if scope == "resource":
                acl = await api.resource_acl(resource, entity_id)
                displayed = acl["override_acl"]
                version = acl["resource_acl_version"]
            else:
                child_type = "record" if scope == "record" else "aggregation"
                acl = await api.child_acl(entity_id, child_type)
                displayed = acl.get("custom_acl", acl.get("effective_acl", []))
                version = acl["version"]
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return

        source_aggregation: dict[str, Any] | None = None
        edited_aggregation: dict[str, Any] | None = None
        owner_resource: dict[str, Any] | None = None
        try:
            if scope != "resource" or resource_type == "aggregation":
                edited_aggregation = await api.get("aggregations", entity_id)
                owner_resource = edited_aggregation
            else:
                owner_resource = await api.get("records", entity_id)
        except ApiError:
            edited_aggregation = None
            owner_resource = None
        owner_name = (
            owner_resource.get("owning_org_unit_name")
            if owner_resource else "this resource's organizational unit"
        )
        source_aggregation_id = acl.get("source_resource_id") or acl.get("effective_acl_source_id")
        if source_aggregation_id:
            try:
                source_aggregation = await api.get("aggregations", int(source_aggregation_id))
            except (ApiError, TypeError, ValueError):
                source_aggregation = None

        options = {
            item["code"]: item["name"]
            for item in ordered_permission_catalogue(catalogue, resource_type)
        }
        role_options = {item["id"]: f"{item['code']} — {item['name']}" for item in roles}
        principals: list[dict[str, Any]] = [dict(item) for item in displayed]
        dialog_title = (
            "Default child aggregation ACL"
            if scope == "aggregation"
            else "Default child record ACL"
            if scope == "record"
            else "Access control list"
        )
        dialog = ui.dialog()
        with dialog, ui.card().classes("max-h-[92vh] p-0 gap-0").style(
            "width: min(1050px, 90vw); max-width: none"
        ):
            with ui.row().classes("w-full items-center px-5 py-4 border-b border-slate-200"):
                ui.icon("policy", color="primary")
                ui.label(dialog_title).classes("text-xl font-semibold grow")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense")
            with ui.element("div").classes(
                "w-full h-[680px] max-h-[calc(92vh-142px)] overflow-y-auto overflow-x-hidden px-5 py-4"
            ):
                if scope == "resource" and acl.get("inherit_acl_from_parent") is not None:
                    with ui.row().classes("w-full items-start gap-3 rounded-lg border border-blue-100 bg-blue-50 p-3"):
                        ui.icon("account_tree", color="primary")
                        with ui.column().classes("gap-0 grow"):
                            ui.label(f"Effective source: {acl_source_label(acl)}").classes("font-semibold text-slate-800")
                            if source_aggregation is not None:
                                ui.label(aggregation_reference_label(source_aggregation)).classes("text-sm text-slate-700")
                            ui.label(
                                "A root aggregation has no parent ACL, so this ACL is necessarily local."
                                if edited_aggregation is not None and edited_aggregation.get("parent_aggregation_id") is None else
                                "Inherited access is evaluated live. A local override remains dormant until inheritance is disabled."
                            ).classes("text-xs text-slate-600")

                        if source_aggregation is not None:
                            async def open_editor_acl_source() -> None:
                                dialog.close()
                                await open_aggregation(source_aggregation)

                            ui.button("Open", icon="open_in_new", on_click=open_editor_acl_source).props(
                                "flat dense no-caps"
                            )
                    inherit = ui.switch("Inherit ACL from parent", value=acl["inherit_acl_from_parent"])
                    if edited_aggregation is not None and edited_aggregation.get("parent_aggregation_id") is None:
                        inherit.set_enabled(False)
                        inherit.tooltip("A root aggregation has no parent ACL to inherit from")
                        ui.label(
                            "This is a root aggregation, so its ACL must be defined locally."
                        ).classes("text-xs text-slate-500 ml-2")
                    if acl.get("override_acl_is_dormant"):
                        ui.label("The local override shown below is dormant while inheritance is enabled.").classes("text-xs text-slate-500")
                else:
                    inherit = None
                if scope == "aggregation":
                    mode = ui.select(
                        {"mirror_resource_acl": "Mirror this aggregation's effective resource ACL", "custom": "Use custom default ACL"},
                        value=acl["mode"], label="Default child aggregation ACL mode",
                    ).classes("w-full mt-3")
                    ui.label("Mirror is a live reference. The custom default ACL is retained dormant when mirror mode is active.").classes("text-xs text-slate-500")
                else:
                    mode = None
                state_banner = ui.column().classes("w-full mt-3")
                editor = ui.column().classes("w-full gap-3 mt-4")
                editor_controls: list[Any] = []
                permission_controls: dict[int, dict[str, Any]] = {}

                def is_dormant() -> bool:
                    if inherit is not None:
                        return bool(inherit.value)
                    if mode is not None:
                        return mode.value == "mirror_resource_acl"
                    return False

                def activate_local_acl() -> None:
                    if inherit is not None:
                        inherit.value = False
                        inherit.update()
                    elif mode is not None:
                        mode.value = "custom"
                        mode.update()
                    render_acl_state()
                    render_principals()

                def render_acl_state() -> None:
                    state_banner.clear()
                    with state_banner:
                        if is_dormant():
                            with ui.card().classes("w-full shadow-none border border-amber-200 bg-amber-50 p-3"):
                                with ui.row().classes("w-full items-start gap-3"):
                                    ui.icon("visibility_off", color="amber-9")
                                    with ui.column().classes("gap-0 grow"):
                                        ui.label(
                                            "Dormant local ACL — not currently used"
                                            if inherit is not None else
                                            "Dormant custom default ACL — not currently used"
                                        ).classes("font-semibold text-amber-950")
                                        ui.label(
                                            "Effective access comes from the parent while inheritance is enabled. "
                                            "The retained local ACL below cannot be edited and has no effect."
                                            if inherit is not None else
                                            "Child aggregations currently mirror this aggregation's effective ACL. "
                                            "The retained custom default ACL below cannot be edited and has no effect."
                                        ).classes("text-xs text-amber-900")
                                    ui.button(
                                        "Use local ACL" if inherit is not None else "Use custom default ACL",
                                        icon="edit", on_click=activate_local_acl,
                                    ).props("outline no-caps color=amber-10")
                        else:
                            with ui.row().classes("w-full items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3"):
                                ui.icon("check_circle", color="positive")
                                ui.label(
                                    "This local ACL is active and changes here affect effective access."
                                    if scope == "resource" else
                                    "This custom default ACL is active and changes affect inheriting children."
                                ).classes("text-sm font-medium text-green-900")

                def render_principals() -> None:
                    editor.clear()
                    editor_controls.clear()
                    permission_controls.clear()
                    with editor:
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label(
                                f"{len(principals)} principal{'s' if len(principals) != 1 else ''}"
                            ).classes("text-sm text-slate-500 grow")
                            add_role_button = ui.button("Add role", icon="person_add", on_click=add_role).props("outline no-caps")
                            editor_controls.append(add_role_button)
                            if not any(item["principal_type"] == "everyone" for item in principals):
                                add_everyone_button = ui.button(
                                    "Add Everyone", icon="groups",
                                    on_click=lambda: (
                                        principals.insert(0, {"principal_type": "everyone", "role_id": None, "permission_codes": []}),
                                        render_principals(),
                                    ),
                                ).props("outline no-caps")
                                editor_controls.append(add_everyone_button)
                            if not any(
                                item["principal_type"] == "org_unit_members"
                                for item in principals
                            ):
                                add_org_members_button = ui.button(
                                    "Add all org unit members", icon="corporate_fare",
                                    on_click=lambda: (
                                        principals.insert(0, {
                                            "principal_type": "org_unit_members",
                                            "role_id": None,
                                            "permission_codes": [],
                                        }),
                                        render_principals(),
                                    ),
                                ).props("outline no-caps")
                                editor_controls.append(add_org_members_button)

                        with ui.row().classes("w-full items-center gap-2 text-slate-500"):
                            ui.icon("groups", size="17px")
                            ui.label(
                                "Everyone represents all authenticated users; global privilege and security-clearance gates still apply."
                            ).classes("text-xs")
                        with ui.row().classes("w-full items-center gap-2 text-slate-500"):
                            ui.icon("corporate_fare", size="17px")
                            ui.label(
                                f"All org unit members means everyone currently working in {owner_name}. "
                                "Membership updates automatically when role assignments change."
                            ).classes("text-xs")

                        ui.label(
                            "Select permissions by principal. Required prerequisites are selected automatically."
                        ).classes("text-xs text-slate-500 mb-2")
                        matrix = ui.element("div").classes(
                            "w-full overflow-auto rounded-xl border border-slate-200 bg-white"
                        ).style("height: 300px")
                        matrix_width = 310 + (len(options) * 132)
                        with matrix:
                            with ui.column().classes("gap-0").style(f"min-width: {matrix_width}px"):
                                with ui.row().classes(
                                    "w-full gap-0 no-wrap border-b border-slate-200 bg-slate-50"
                                ).style("position: sticky; top: 0; z-index: 30"):
                                    with ui.element("div").classes(
                                        "w-[310px] shrink-0 self-stretch px-3 py-3 bg-slate-50 border-r border-slate-200"
                                    ).style("position: sticky; left: 0; z-index: 35"):
                                        ui.label("Principal").classes("text-xs font-semibold uppercase tracking-wide text-slate-500")
                                    for code, name in options.items():
                                        with ui.element("div").classes(
                                            "w-[132px] shrink-0 self-stretch px-2 py-3 border-r border-slate-200 text-center"
                                        ):
                                            ui.label(operation_label(code)).classes(
                                                "text-xs font-semibold leading-tight text-slate-600"
                                            ).tooltip(name)

                                if not principals:
                                    ui.label(
                                        "No principals are present. Add a role, Everyone, or all org unit members to grant resource permissions."
                                    ).classes("m-5 text-sm text-slate-500")

                                for index, principal in enumerate(principals):
                                    selected = set(principal.get("permission_codes", []))
                                    row_controls: dict[str, Any] = {}
                                    permission_controls[id(principal)] = row_controls
                                    with ui.row().classes(
                                        "w-full gap-0 no-wrap border-b border-slate-100 last:border-b-0 hover:bg-blue-50/30"
                                    ):
                                        with ui.element("div").classes(
                                            "w-[310px] shrink-0 min-h-[62px] bg-white border-r border-slate-200 px-2 py-1"
                                        ).style("position: sticky; left: 0; z-index: 20"):
                                            with ui.row().classes("w-full no-wrap items-center gap-2"):
                                                ui.icon(
                                                    {
                                                        "everyone": "groups",
                                                        "org_unit_members": "corporate_fare",
                                                    }.get(principal["principal_type"], "badge"),
                                                    color="primary", size="20px",
                                                )
                                                if principal["principal_type"] == "everyone":
                                                    with ui.column().classes("gap-0 grow min-w-0"):
                                                        ui.label("Everyone").classes("font-semibold")
                                                        ui.label("All authenticated users").classes("text-xs text-slate-500")
                                                elif principal["principal_type"] == "org_unit_members":
                                                    with ui.column().classes("gap-0 grow min-w-0"):
                                                        ui.label("All org unit members").classes("font-semibold")
                                                        ui.label(
                                                            f"Everyone currently working in {owner_name}"
                                                        ).classes("text-xs text-slate-500")
                                                else:
                                                    role_picker = ui.select(
                                                        role_options, value=principal.get("role_id"),
                                                    ).props(
                                                        "dense outlined options-dense use-input input-debounce=0"
                                                    ).classes("grow min-w-0")
                                                    role_picker.on_value_change(
                                                        lambda event, item=principal: item.update(role_id=event.value)
                                                    )
                                                    editor_controls.append(role_picker)
                                                    browse_role_button = ui.button(
                                                        icon="account_tree",
                                                        on_click=lambda _, control=role_picker: show_organization_structure(
                                                            selection_mode="role", target_control=control,
                                                        ),
                                                    ).props(
                                                        "flat round dense aria-label='Browse roles'"
                                                    ).tooltip("Browse organization structure for a role")
                                                    editor_controls.append(browse_role_button)
                                                remove_button = ui.button(
                                                    icon="delete_outline", color="negative",
                                                    on_click=lambda _, i=index: (principals.pop(i), render_principals()),
                                                ).props("flat round dense").tooltip("Remove principal")
                                                editor_controls.append(remove_button)

                                        for code in options:
                                            with ui.element("div").classes(
                                                "w-[132px] shrink-0 min-h-[62px] border-r border-slate-100 flex items-center justify-center"
                                            ):
                                                checkbox = ui.checkbox(value=code in selected).props("dense")
                                                checkbox.tooltip(options[code])
                                                row_controls[code] = checkbox
                                                editor_controls.append(checkbox)

                                                def update_permission(
                                                    event: Any, item=principal, permission=code,
                                                ) -> None:
                                                    current = set(item.get("permission_codes", []))
                                                    if bool(event.value):
                                                        updated = permission_closure(current | {permission})
                                                        added = updated - current - {permission}
                                                        if added:
                                                            ui.notify(
                                                                "Required prerequisite permissions were added",
                                                                color="info",
                                                            )
                                                    else:
                                                        removed_dependents = dependents_of(permission, current)
                                                        updated = current - {permission} - removed_dependents
                                                        if removed_dependents:
                                                            ui.notify(
                                                                "Dependent permissions were also removed",
                                                                color="info",
                                                            )
                                                    item["permission_codes"] = sorted(updated)
                                                    for permission_code, control in permission_controls.get(id(item), {}).items():
                                                        expected = permission_code in updated
                                                        if bool(control.value) != expected:
                                                            control.value = expected
                                                            control.update()

                                                checkbox.on_value_change(update_permission)

                def add_role() -> None:
                    if any(
                        item["principal_type"] == "role" and item.get("role_id") is None
                        for item in principals
                    ):
                        ui.notify("Select the blank role before adding another", color="warning")
                        return
                    principals.append({"principal_type": "role", "role_id": None, "permission_codes": []})
                    render_principals()

                def apply_editor_state() -> None:
                    dormant = is_dormant()
                    editor.classes(replace="w-full gap-3 mt-4 " + ("opacity-55" if dormant else ""))
                    for control in editor_controls:
                        control.set_enabled(not dormant)

                original_render_principals = render_principals
                def render_principals() -> None:
                    original_render_principals()
                    apply_editor_state()

                if inherit is not None:
                    inherit.on_value_change(lambda _: (render_acl_state(), render_principals()))
                if mode is not None:
                    mode.on_value_change(lambda _: (render_acl_state(), render_principals()))
                render_acl_state()
                render_principals()
                reason = ui.input("Reason for access change").classes("w-full mt-4")

            async def save_acl() -> None:
                if any(
                    item["principal_type"] == "role" and item.get("role_id") is None
                    for item in principals
                ):
                    ui.notify("Select a role for every role row before saving", color="warning")
                    return
                if not reason.value or not str(reason.value).strip():
                    ui.notify("A reason is required", color="warning"); return
                payload: dict[str, Any] = {"version": version, "grants": principals, "reason": str(reason.value).strip()}
                if inherit is not None: payload["inherit_acl_from_parent"] = inherit.value
                if mode is not None: payload["mode"] = mode.value
                async def apply_change() -> None:
                    try:
                        if scope == "resource": await api.replace_resource_acl(resource, entity_id, payload)
                        else: await api.replace_child_acl(entity_id, "record" if scope == "record" else "aggregation", payload)
                        dialog.close(); ui.notify("Access control list updated", color="positive")
                        if on_saved:
                            result = on_saved()
                            if inspect.isawaitable(result): await result
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                try:
                    if scope == "resource":
                        await apply_change(); return
                    impact = await api.preview_child_acl(
                        entity_id, "record" if scope == "record" else "aggregation", payload,
                    )
                    confirmation = ui.dialog()
                    with confirmation, ui.card().classes("w-[520px] max-w-full"):
                        ui.label("Apply inherited access change?").classes("text-lg font-semibold")
                        ui.label(
                            f"This changes {impact['added_grants']} grants added and "
                            f"{impact['removed_grants']} removed across "
                            f"{impact.get('affected_aggregation_count', 0)} inheriting aggregations and "
                            f"{impact.get('affected_record_count', 0)} inheriting records. "
                            f"Up to {impact['potentially_affected_user_count']} users may be affected."
                        ).classes("text-sm text-slate-600")
                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=confirmation.close).props("flat no-caps")
                            async def confirm_apply() -> None:
                                confirmation.close(); await apply_change()
                            ui.button("Apply change", icon="check", on_click=confirm_apply).props("unelevated no-caps")
                    confirmation.open()
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)
            with ui.row().classes("w-full justify-end gap-2 px-5 py-4 border-t border-slate-200"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Save ACL", icon="save", on_click=save_acl).props("unelevated no-caps")
        dialog.open()

    async def show_access_explanation(resource_type: str, entity_id: int) -> None:
        """Explain every authorization gate without treating the UI as an enforcement boundary."""
        privileges = set((auth_state.get("principal") or {}).get("global_privileges", []))
        can_examine_others = "authorization.explain" in privileges
        users: list[dict[str, Any]] = []
        if can_examine_others:
            try:
                users = await api.explainable_users()
            except ApiError:
                can_examine_others = False
        operations = {code: operation_label(code) for code in OPERATIONS[resource_type]}
        dialog = ui.dialog()
        result_host: Any = None
        explanation_request = {"sequence": 0}
        with dialog, ui.card().classes("w-[820px] max-w-[95vw] max-h-[90vh] p-0 gap-0"):
            with ui.row().classes("w-full items-center border-b border-slate-200 px-5 py-4"):
                ui.icon("fact_check", color="primary")
                with ui.column().classes("gap-0 grow"):
                    ui.label("Access explanation").classes("text-xl font-semibold")
                    ui.label("Shows which policy gates and roles contribute to the decision.").classes("text-xs text-slate-500")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense aria-label='Close access explanation'")
            with ui.row().classes("w-full items-end gap-3 px-5 pt-4"):
                operation = ui.select(operations, value=OPERATIONS[resource_type][0], label="Operation").props("outlined").classes("grow")
                user = None
                if can_examine_others:
                    user = ui.select(
                        {item["id"]: f"{item['name']} — {item.get('email') or 'no email'}" for item in users},
                        label="Explain for another user (optional)", clearable=True,
                    ).props("outlined use-input").classes("grow")
                run = ui.button("Explain", icon="play_arrow").props("unelevated no-caps")
            result_host = ui.scroll_area().classes("w-full h-[520px] px-5 py-4")

            async def load_explanation() -> None:
                explanation_request["sequence"] += 1
                request_sequence = explanation_request["sequence"]
                selected_operation = operation.value
                try:
                    result = await api.explain_access({
                        "resource_type": resource_type, "resource_id": entity_id,
                        "operation": selected_operation,
                        **({"user_id": user.value} if user is not None and user.value else {}),
                    })
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True); return
                if (
                    request_sequence != explanation_request["sequence"]
                    or selected_operation != operation.value
                ):
                    return
                source_aggregation: dict[str, Any] | None = None
                source_aggregation_id = result.get("acl", {}).get("source_resource_id")
                if source_aggregation_id:
                    try:
                        source_aggregation = await api.get("aggregations", int(source_aggregation_id))
                    except (ApiError, TypeError, ValueError):
                        # A source ancestor can legitimately be hidden by the same
                        # authorization policy this dialog is explaining.
                        source_aggregation = None
                result_host.clear()
                roles = {item["role_id"]: item for item in result["subject"]["effective_roles"]}
                with result_host:
                    with ui.row().classes(
                        "w-full items-center gap-3 rounded-xl border p-4 " +
                        ("border-green-200 bg-green-50" if result["allowed"] else "border-red-200 bg-red-50")
                    ):
                        ui.icon("check_circle" if result["allowed"] else "cancel", color="positive" if result["allowed"] else "negative", size="28px")
                        with ui.column().classes("gap-0 grow"):
                            ui.label("Allowed" if result["allowed"] else "Denied").classes("text-lg font-semibold")
                            ui.label(str(result["decision_code"]).replace("_", " ").title()).classes("text-sm text-slate-600")
                    ui.label("Decision gates").classes("text-base font-semibold mt-4")
                    for gate in result["gates"]:
                        with ui.row().classes("w-full items-start gap-3 py-2 border-b border-slate-100"):
                            ui.icon("check_circle" if gate["passed"] else "cancel", color="positive" if gate["passed"] else "negative")
                            with ui.column().classes("gap-0 grow"):
                                ui.label(GATE_LABELS.get(gate["gate"], gate["gate"].replace("_", " ").title())).classes("font-medium")
                                ui.label(gate_detail(gate)).classes("text-xs text-slate-500")
                    ui.label("Contributing context").classes("text-base font-semibold mt-4")
                    with ui.grid(columns=2).classes("w-full gap-3"):
                        with ui.column().classes("gap-0 rounded-lg border border-slate-200 p-3"):
                            ui.label("Effective clearance").classes(
                                "text-xs font-semibold uppercase tracking-wide text-slate-500"
                            )
                            ui.label(
                                security_level_label(result.get("effective_security_level"))
                            ).classes("text-sm font-medium text-slate-800")
                        with ui.column().classes("gap-0 rounded-lg border border-slate-200 p-3"):
                            ui.label("Required clearance").classes(
                                "text-xs font-semibold uppercase tracking-wide text-slate-500"
                            )
                            ui.label(
                                security_level_label(result.get("required_security_level"))
                            ).classes("text-sm font-medium text-slate-800")
                    with ui.column().classes("w-full gap-1 rounded-lg border border-slate-200 bg-slate-50 p-3"):
                        ui.label("ACL source").classes("text-xs font-semibold uppercase tracking-wide text-slate-500")
                        ui.label(
                            acl_source_label(result.get("acl", {}))
                        ).classes("text-sm font-medium text-slate-800")
                        if source_aggregation is not None:
                            with ui.row().classes("w-full items-center gap-2"):
                                ui.icon("folder", color="primary", size="18px")
                                ui.label(
                                    aggregation_reference_label(source_aggregation)
                                ).classes("text-sm text-slate-700 grow")

                                async def open_acl_source() -> None:
                                    dialog.close()
                                    await open_aggregation(source_aggregation)

                                ui.button("Open", icon="open_in_new", on_click=open_acl_source).props(
                                    "flat dense no-caps"
                                )
                        elif source_aggregation_id:
                            ui.label(
                                f"Aggregation reference #{source_aggregation_id} · details hidden by access policy"
                            ).classes("text-xs text-slate-500")
                    contributors = result["contributors"]

                    def contributor_heading(title: str, code: str, icon: str) -> None:
                        with ui.row().classes("w-full items-start gap-3"):
                            ui.icon(icon, color="primary", size="20px").classes("mt-1")
                            with ui.column().classes("gap-0 grow min-w-0"):
                                ui.label(title).classes("text-sm font-semibold text-slate-800")
                                ui.label(code).classes("text-xs font-mono text-slate-400")

                    def contributor_role(role_id: int, *, clearance: bool = False) -> None:
                        role = roles.get(role_id, {})
                        with ui.row().classes("w-full items-center gap-2 pl-8"):
                            ui.icon("badge", color="blue-grey-5", size="16px")
                            ui.label(
                                f"{role.get('role_code', 'Role')} — "
                                f"{role.get('role_name', role_id)}"
                            ).classes("text-sm text-slate-700")
                            if clearance:
                                ui.label(
                                    f"{role.get('security_level_code', '—')} · "
                                    f"level {role.get('clearance', '—')}"
                                ).classes("text-xs text-slate-400")

                    privilege_role_ids = contributors.get("privilege_role_ids", [])
                    if privilege_role_ids:
                        with ui.column().classes("w-full gap-1 rounded-lg border border-slate-200 p-3"):
                            required_privilege = result["required_privilege"]
                            contributor_heading(
                                f"Global privilege: {authorization_code_label(required_privilege)}",
                                required_privilege, "key",
                            )
                            for role_id in privilege_role_ids:
                                contributor_role(role_id)

                    clearance_role_ids = contributors.get("clearance_role_ids", [])
                    if clearance_role_ids:
                        with ui.column().classes("w-full gap-1 rounded-lg border border-slate-200 p-3"):
                            contributor_heading(
                                f"Security clearance: level {result.get('required_clearance', '—')} required",
                                "Maximum clearance across effective roles", "verified_user",
                            )
                            for role_id in clearance_role_ids:
                                contributor_role(role_id, clearance=True)

                    everyone_permissions = contributors.get("everyone_permissions", [])
                    org_unit_member_permissions = contributors.get(
                        "org_unit_member_permissions", []
                    )
                    org_unit_member_roles = contributors.get(
                        "org_unit_member_role_ids_by_permission", {}
                    )
                    acl_roles = contributors.get("acl_role_ids_by_permission", {})
                    for permission in dict.fromkeys([
                        *everyone_permissions,
                        *org_unit_member_permissions,
                        *acl_roles.keys(),
                    ]):
                        role_ids = acl_roles.get(permission, [])
                        if (
                            permission not in everyone_permissions
                            and permission not in org_unit_member_permissions
                            and not role_ids
                        ):
                            continue
                        with ui.column().classes("w-full gap-1 rounded-lg border border-slate-200 p-3"):
                            contributor_heading(
                                f"ACL permission: {authorization_code_label(permission)}",
                                permission, "policy",
                            )
                            if permission in everyone_permissions:
                                with ui.row().classes("w-full items-center gap-2 pl-8"):
                                    ui.icon("groups", color="blue-grey-5", size="16px")
                                    ui.label("Everyone — all authenticated users").classes("text-sm text-slate-700")
                            if permission in org_unit_member_permissions:
                                with ui.column().classes("w-full gap-1 pl-8"):
                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.icon("corporate_fare", color="blue-grey-5", size="16px")
                                        ui.label(
                                            "All org unit members — matched through the resource owner"
                                        ).classes("text-sm text-slate-700")
                                    for role_id in org_unit_member_roles.get(permission, []):
                                        contributor_role(role_id)
                            for role_id in role_ids:
                                contributor_role(role_id)

                    bypass_role_ids = contributors.get("governance_bypass_role_ids", [])
                    if bypass_role_ids:
                        with ui.column().classes("w-full gap-1 rounded-lg border border-amber-200 bg-amber-50 p-3"):
                            contributor_heading(
                                "Information-governance ACL bypass",
                                "The ACL gate was bypassed; privilege and clearance gates still apply.",
                                "admin_panel_settings",
                            )
                            for role_id in bypass_role_ids:
                                contributor_role(role_id)
                    if result["acl"].get("dormant_override_grants"):
                        ui.label("A dormant local ACL override is retained but does not affect this decision.").classes("text-xs text-amber-800 bg-amber-50 rounded p-2 mt-2")
            run.on("click", load_explanation)
            operation.on_value_change(lambda _: load_explanation())
            if user is not None:
                user.on_value_change(lambda _: load_explanation())
        dialog.open()
        await load_explanation()

    async def show_governed_move(
        resource: str, item: dict[str, Any], on_saved,
    ) -> None:
        try:
            aggregations = await api.list("aggregations")
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        options = relationship_options(
            [row for row in aggregations if not (
                resource == "aggregations" and row["id"] == item["id"]
            )], ("aggregation_number", "title"),
        )
        dialog = ui.dialog()
        preview_host: Any = None
        preview_state: dict[str, Any] = {}
        with dialog, ui.card().classes("w-[680px] max-w-full gap-4"):
            ui.label(f"Move {resource.rstrip('s')}").classes("text-xl font-semibold")
            destination = ui.select(options, label="Destination aggregation").props(
                "outlined options-dense"
            ).classes("w-full")
            keep_access = ui.checkbox("Keep current effective access as a local override")
            reason = ui.textarea("Reason", placeholder="Required").props(
                "outlined autogrow"
            ).classes("w-full")
            preview_host = ui.column().classes("w-full gap-2")

            async def refresh_preview() -> None:
                preview_host.clear()
                preview_state.clear()
                if destination.value is None:
                    return
                try:
                    preview = await api.acl_move_preview(
                        resource, item["id"], int(destination.value),
                        keep_current_access_as_override=bool(keep_access.value),
                    )
                except ApiError as error:
                    with preview_host:
                        ui.label(error_message(error)).classes("text-sm text-negative")
                    return
                preview_state.update(preview)
                with preview_host:
                    ui.label(
                        f"ACL impact: {preview['added_count']} grants added · {preview['removed_count']} removed"
                    ).classes("text-sm font-medium")
                    if resource == "aggregations":
                        impact = preview.get("affected_subtree", {})
                        ui.label(
                            f"Subtree: {impact.get('aggregation_count', 0)} aggregations · "
                            f"{impact.get('record_count', 0)} records"
                        ).classes("text-sm text-slate-600")
                    if preview.get("ownership_changes"):
                        ui.label(
                            "This move changes organizational ownership and retargets All org unit members."
                        ).classes("text-sm font-medium text-amber-900 bg-amber-50 rounded p-2")

            destination.on_value_change(lambda _: refresh_preview())
            keep_access.on_value_change(lambda _: refresh_preview())

            async def submit() -> None:
                if destination.value is None or not (reason.value or "").strip():
                    ui.notify("Destination and reason are required", color="warning")
                    return
                if not preview_state:
                    await refresh_preview()
                if not preview_state:
                    return
                try:
                    saved = await api.move_with_acl(resource, item["id"], {
                        "destination_aggregation_id": int(destination.value),
                        "resource_version": item["version"],
                        "keep_current_access_as_override": bool(keep_access.value),
                        "confirm_ownership_change": bool(preview_state.get("ownership_changes")),
                        "reason": reason.value.strip(),
                    })
                    dialog.close()
                    ui.notify("Resource moved", color="positive")
                    await on_saved(saved)
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Move", icon="drive_file_move", on_click=submit).props("unelevated no-caps")
        dialog.open()

    async def show_ownership_correction(root: dict[str, Any], on_saved) -> None:
        try:
            rows = await api.ownership_correction_options()
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        rows = [row for row in rows if row["org_unit_id"] != root["owning_org_unit_id"]]
        dialog = ui.dialog()
        preview_host: Any = None
        preview_state: dict[str, Any] = {}
        with dialog, ui.card().classes("w-[680px] max-w-full gap-4"):
            ui.label("Correct ownership").classes("text-xl font-semibold")
            ui.label(
                "Use this governed correction only when the root aggregation was created for the wrong organizational unit."
            ).classes("text-sm text-slate-600")
            destination = ui.select(
                {row["role_id"]: row["label"] for row in rows},
                label="Correct owner and creator ACL role",
            ).props("outlined options-dense").classes("w-full")
            reason = ui.textarea("Reason", placeholder="Required").props(
                "outlined autogrow"
            ).classes("w-full")
            preview_host = ui.column().classes("w-full gap-2")

            async def refresh_preview() -> None:
                preview_host.clear(); preview_state.clear()
                if destination.value is None:
                    return
                try:
                    preview = await api.ownership_correction_preview(
                        root["id"], int(destination.value)
                    )
                except ApiError as error:
                    with preview_host:
                        ui.label(error_message(error)).classes("text-sm text-negative")
                    return
                preview_state.update(preview)
                with preview_host:
                    ui.label(
                        f"Affected holdings: {preview['affected_aggregation_count']} aggregations · "
                        f"{preview['affected_record_count']} records"
                    ).classes("text-sm font-medium")
                    ui.label(
                        f"Creator-role grants reassigned: {preview['creator_role_grant_count']}"
                    ).classes("text-sm text-slate-600")
                    ui.label(
                        "All org unit members will immediately refer to the corrected owner. Other named-role grants remain unchanged."
                    ).classes("text-sm text-amber-900 bg-amber-50 rounded p-2")

            destination.on_value_change(lambda _: refresh_preview())

            async def submit() -> None:
                if destination.value is None or not (reason.value or "").strip():
                    ui.notify("Correct owner and reason are required", color="warning")
                    return
                if not preview_state:
                    await refresh_preview()
                if not preview_state:
                    return
                try:
                    saved = await api.correct_ownership(
                        root["id"], int(destination.value), reason.value.strip()
                    )
                    dialog.close()
                    ui.notify("Organizational ownership corrected", color="positive")
                    await on_saved(saved)
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Confirm correction", icon="published_with_changes", on_click=submit).props(
                    "unelevated no-caps color=negative"
                )
        dialog.open()

    async def show_record_details(record: dict[str, Any]) -> None:
        """Navigate to the dedicated details page for a record."""
        await select_record_details(record["id"])

    async def select_record_details(record_id: int) -> None:
        register_navigation("record-details", f"Record #{record_id}", entity_id=record_id)
        previous_resource = state.get("resource")
        if previous_resource != "record-details":
            state["record_detail_return_resource"] = previous_resource
            state["record_detail_return_aggregation"] = state.get("aggregation_detail")
        show_authenticated_view()
        state.update(resource="record-details", record_detail_id=record_id, rows=[], searched=True)
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        guidance.text = ""
        table_container.clear()

        try:
            fetched = await api.get("records", record_id)
            record = (await decorate_for_spec(ENTITIES["records"], [fetched]))[0]
            security_level = await api.get("security-levels", record["security_level_id"])
            capabilities = await api.resource_capabilities("records", record_id)
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return

        title.text = record["title"]
        subtitle.text = f"Record {record['record_number']}"
        register_navigation(
            "record-details", record["title"], entity_id=record_id,
            accessible_label=f"{record['title']} — {record['record_number']}",
        )

        async def refresh_record_view(saved: dict[str, Any] | None = None) -> None:
            await select_record_details((saved or record)["id"])

        async def leave_record_page() -> None:
            await breadcrumb_back(lambda: select_entity("records"))

        async def open_containing_aggregation() -> None:
            try:
                await open_aggregation(await api.get("aggregations", record["aggregation_id"]))
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def confirm_delete_record() -> None:
            confirmation = ui.dialog()
            try:
                components = await api.components(record["id"])
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
                return
            with confirmation, ui.card().classes("w-[500px] max-w-full"):
                ui.label("Delete record?").classes("text-xl font-semibold")
                ui.label(
                    f"{record['record_number']} — {record['title']} will be permanently deleted."
                ).classes("text-sm text-slate-700")
                if components:
                    ui.label(
                        f"Its {len(components)} digital component{'s' if len(components) != 1 else ''} "
                        "and all stored content will also be permanently deleted."
                    ).classes("text-sm font-medium text-negative")
                ui.label("The immutable event history will be retained.").classes("text-xs text-slate-500")

                async def delete_record() -> None:
                    try:
                        await api.delete("records", record["id"], record["version"])
                        confirmation.close()
                        ui.notify("Record deleted", color="positive")
                        await load_recent(ENTITIES["records"])
                        await leave_record_page()
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=confirmation.close).props("flat no-caps")
                    ui.button(
                        "Delete record", icon="delete_forever", color="negative",
                        on_click=delete_record,
                    ).props("unelevated no-caps")
            confirmation.open()

        with table_container, ui.column().classes("w-full p-5 gap-5"):
            with ui.card().classes("detail-surface w-full shadow-none p-0 gap-0 overflow-hidden"):
                with ui.row().classes("w-full items-center px-5 py-3 border-b border-slate-100"):
                    ui.icon("description", color="primary", size="21px")
                    ui.label("Record details").classes("font-semibold")
                with ui.row().classes(f"w-full {RECORD_DETAIL_HEADER_CLASSES} gap-3 px-5 py-5"):
                    ui.avatar(icon="description", color="blue-1", text_color="primary", size="52px")
                    with ui.column().classes(RECORD_DETAIL_TITLE_CLASSES):
                        ui.label(record["title"]).classes("text-2xl font-semibold leading-tight break-words")
                        ui.label(record["record_number"]).classes("text-sm text-slate-500 font-medium mt-1")
                    favourite_button("records", record["id"])
                    ui.button("Back", icon="arrow_back", on_click=leave_record_page).props("flat no-caps color=blue-grey-8")
                    if not record.get("_effectively_closed") and capabilities.get("modify_metadata"):
                        ui.button(
                            "Edit metadata", icon="edit",
                            on_click=lambda: open_editor(
                                record, on_saved=refresh_record_view, resource_key="records",
                            ),
                        ).props("outline no-caps color=primary")
                    if not record.get("_effectively_closed") and capabilities.get("delete"):
                        ui.button(
                            "Delete", icon="delete_outline", color="negative",
                            on_click=confirm_delete_record,
                        ).props("flat no-caps")
                    ui.button(
                        "Event history", icon="history",
                        on_click=lambda: show_entity_history("records", record),
                    ).props("flat no-caps")
                    ui.button(
                        "Why this access?", icon="fact_check",
                        on_click=lambda: show_access_explanation("record", record["id"]),
                    ).props("flat no-caps").tooltip("Explain the authorization decision gate by gate")
                    if capabilities.get("manage_acl"):
                        ui.button(
                            "Access", icon="policy",
                            on_click=lambda: show_acl_editor(
                                "records", record["id"], on_saved=lambda: refresh_record_view(),
                            ),
                        ).props("flat no-caps")
                if not record.get("_effectively_closed") and capabilities.get("move"):
                    with ui.expansion(
                        "Advanced", caption="Specialist record actions", icon="tune", value=False,
                    ).classes(
                        "w-full border-t border-slate-100 px-5"
                    ):
                        with ui.row().classes("w-full justify-end gap-2 pb-4"):
                            ui.button(
                                "Move", icon="drive_file_move",
                                on_click=lambda: show_governed_move(
                                    "records", record, refresh_record_view,
                                ),
                            ).props("flat dense no-caps")
                ui.separator()
                with ui.column().classes("w-full px-5 py-4 gap-4"):
                    if record.get("_effectively_closed"):
                        with ui.row().classes("w-full items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg"):
                            ui.icon("lock", color="amber-8")
                            ui.label("This record is read-only because its aggregation hierarchy is closed.").classes("text-sm text-amber-900")
                    if record.get("description"):
                        with ui.column().classes("w-full gap-1 rounded-xl bg-slate-50 px-4 py-3"):
                            ui.label("DESCRIPTION").classes("detail-field-label")
                            ui.label(record["description"]).classes(
                                "w-full text-sm leading-6 text-slate-600 whitespace-pre-wrap"
                            )
                    with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-0"):
                        for label, value in (
                            ("Record status", "Read-only" if record.get("_effectively_closed") else "Active"),
                            ("Security level", f"{security_level['code']} — {security_level['name']}"),
                            (
                                "Owning organizational unit",
                                f"{record['owning_org_unit_code']} — {record['owning_org_unit_name']}",
                            ),
                            ("Originated", format_timestamp(record.get("date_originated"))),
                            ("Created", format_timestamp(record.get("date_created"))),
                            ("Containing aggregation", record.get("aggregation_display")),
                        ):
                            with ui.column().classes("detail-field gap-1"):
                                ui.label(label).classes("detail-field-label")
                                if label == "Containing aggregation" and isinstance(value, dict):
                                    aggregation_label = " — ".join(filter(None, (value.get("code"), value.get("name"))))
                                    ui.button(
                                        aggregation_label,
                                        on_click=open_containing_aggregation,
                                    ).props("flat dense no-caps color=primary align=left").classes(
                                        "font-semibold self-start -ml-2"
                                    )
                                elif label == "Record status":
                                    ui.badge(
                                        str(value),
                                        color="amber-8" if record.get("_effectively_closed") else "positive",
                                    ).props("outline")
                                else:
                                    ui.label(str(value or "—")).classes("detail-field-value")

            with ui.card().classes("detail-surface w-full shadow-none p-5 gap-4"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon("attach_file", color="primary", size="28px")
                    with ui.column().classes("gap-0 grow"):
                        ui.label("Digital components").classes("text-xl font-semibold")
                        ui.label("Files belonging to this record can be managed directly here.").classes("text-sm text-slate-500")
                components_host = ui.column().classes("w-full gap-3")
                await show_components(record, container=components_host)

    async def decorate_for_spec(
        spec: EntitySpec, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if spec.key == "classifications":
            schemes = await api.list("classification-schemes")
            schemes_by_id = {item["id"]: item for item in schemes}
            return [{
                **item,
                "type_display": {
                    "name": "Terminal" if item.get("is_terminal") else "Branch",
                    "code": "Assignable" if item.get("is_terminal") else "Hierarchy",
                },
                "scheme_display": relationship_cell(
                    schemes_by_id.get(item.get("classification_scheme_id"))
                ),
            } for item in rows]
        if spec.key == "aggregations":
            all_aggregations = await api.list("aggregations")
            by_id = {item["id"]: item for item in all_aggregations}
            return [
                {
                    **item,
                    "_effectively_closed": effective_closure(
                        by_id.get(item["id"], item), by_id
                    ) is not None,
                    "_directly_closed": bool(item.get("date_closed")),
                }
                for item in rows
            ]
        if spec.key == "org-units":
            all_units = await api.list("org-units")
            by_id = {item["id"]: item for item in all_units}
            decorated = decorate_relationship_rows(spec.key, rows, all_units)
            result = []
            for item in decorated:
                source = inactive_org_unit_source(by_id.get(item["id"], item), by_id)
                result.append({
                    **item,
                    "effective_status": "inactive" if source else "active",
                    "_inactive_reason": (
                        "Directly inactive" if source and source["id"] == item["id"]
                        else f"Inherited from {source['code']} — {source['name']}" if source
                        else "Active"
                    ),
                })
            return result
        if spec.key == "roles":
            units, profiles = await asyncio.gather(
                api.list("org-units"), api.profile_references(),
            )
            by_id = {item["id"]: item for item in units}
            profiles_by_id = {item["id"]: item for item in profiles}
            decorated = decorate_relationship_rows(spec.key, rows, units)
            result = []
            for item in decorated:
                source = inactive_org_unit_source(by_id.get(item.get("org_unit_id")), by_id)
                effective = item.get("status") == "active" and source is None
                result.append({
                    **item,
                    "profile_display": relationship_cell(
                        profiles_by_id.get(item.get("profile_id"))
                    ),
                    "effective_status": "active" if effective else "inactive",
                    "_inactive_reason": (
                        "Role is directly inactive" if item.get("status") == "inactive"
                        else f"Organization inactive: {source['code']} — {source['name']}" if source
                        else "Active"
                    ),
                })
            return result
        if spec.key == "users":
            return [
                {
                    **item,
                    "_avatar": user_avatar(item),
                    "_inactive_reason": item.get("status", "active").title(),
                }
                for item in rows
            ]
        if spec.key == "records":
            aggregations = await api.list("aggregations")
            by_id = {item["id"]: item for item in aggregations}
            decorated = decorate_relationship_rows(spec.key, rows, aggregations)
            return [
                {
                    **item,
                    "_effectively_closed": effective_closure(
                        by_id.get(item.get("aggregation_id")), by_id
                    ) is not None,
                }
                for item in decorated
            ]
        return rows

    async def load_recent(spec: EntitySpec) -> None:
        if not spec.search_first:
            state["recent_created"] = []
            state["recent_updated"] = []
            return
        if spec.key == "classifications":
            state["recent_created"] = []
            state["recent_updated"] = []
            return
        created, updated = await api.recently_created(spec.key), await api.recently_updated(spec.key)
        state["recent_created"] = await decorate_for_spec(spec, created)
        state["recent_updated"] = await decorate_for_spec(spec, updated)

    async def open_record_draft_editor(
        target_aggregation_id: int | None = None, on_committed=None,
    ) -> None:
        spec = ENTITIES["records"]
        try:
            draft = await api.create_record_draft()
            aggregations, security_levels, creation_roles = await asyncio.gather(
                api.list("aggregations"), api.list("security-levels"),
                api.creation_role_options(target_aggregation_id),
            )
            aggregations_by_id = {item["id"]: item for item in aggregations}
            aggregations = [
                item for item in aggregations
                if effective_closure(item, aggregations_by_id) is None
            ]
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return

        dialog = ui.dialog().props("persistent")
        controls: dict[str, Any] = {}
        current_rows: list[dict[str, Any]] = []
        component_area: Any = None
        upload_lock = asyncio.Lock()
        upload_state = {"pending": 0}
        action_controls: dict[str, Any] = {}
        uploader_control: dict[str, Any] = {}

        async def refresh_draft_components() -> None:
            try:
                rows = await api.draft_components(draft["id"])
                current_rows.clear()
                current_rows.extend(rows)
                component_area.clear()
                component_list.set_visibility(bool(rows))
                with component_area:
                    if rows:
                        render_component_cards(rows, move_draft_component, remove_draft_component)
            except ApiError as error:
                with component_area:
                    ui.notify(error_message(error), color="negative")

        async def move_draft_component(component: dict[str, Any], direction: int) -> None:
            index = next((i for i, item in enumerate(current_rows) if item["id"] == component["id"]), -1)
            target = index + direction
            if index < 0 or target < 0 or target >= len(current_rows):
                return
            reordered = list(current_rows)
            reordered[index], reordered[target] = reordered[target], reordered[index]
            try:
                await api.reorder_draft_components(draft["id"], [
                    {"id": item["id"], "component_order": position}
                    for position, item in enumerate(reordered, 1)
                ])
                await refresh_draft_components()
            except ApiError as error:
                ui.notify(error_message(error), color="negative")

        async def remove_draft_component(component: dict[str, Any]) -> None:
            try:
                await api.delete_draft_component(draft["id"], component["id"])
                ui.notify("Staged file removed", color="positive")
                await refresh_draft_components()
            except ApiError as error:
                ui.notify(error_message(error), color="negative")

        def upload_to_draft(event: events.MultiUploadEventArguments) -> None:
            try:
                buffered_files = buffer_upload_batch(event)
            except (OSError, ValueError) as error:
                ui.notify(f"Could not read an uploaded file: {error}", color="negative", close_button=True)
                return
            upload_state["pending"] += 1
            action_controls["commit"].disable()
            action_controls["upload_wait"].set_visibility(True)

            async def stage_buffered_files() -> None:
                try:
                    async with upload_lock:
                        await refresh_draft_components()
                        first_position = len(current_rows) + 1
                        for offset, (content, name, mime_type) in enumerate(buffered_files):
                            await api.upload_draft_component(
                                draft["id"], first_position + offset, name, content, mime_type,
                            )
                            await refresh_draft_components()
                    with component_area:
                        ui.notify(
                            f"{len(buffered_files)} file{'s' if len(buffered_files) != 1 else ''} staged for this record",
                            color="positive",
                        )
                    uploader_control["uploader"].reset()
                except ApiError as error:
                    with component_area:
                        ui.notify(error_message(error), color="negative", close_button=True)
                finally:
                    upload_state["pending"] -= 1
                    if upload_state["pending"] == 0:
                        action_controls["commit"].enable()
                        action_controls["upload_wait"].set_visibility(False)

            background_tasks.create(
                stage_buffered_files(), name=f"stage components for draft {draft['id']}"
            )

        async def discard() -> None:
            try:
                await api.discard_record_draft(draft["id"])
            except ApiError as error:
                if error.status_code != 404:
                    ui.notify(error_message(error), color="negative")
                    return
            dialog.close()

        async def commit() -> None:
            try:
                payload = form_payload(spec, controls, creating=True)
                creator_role_id = controls["creator_acl_role_id"].value
                if creator_role_id is None:
                    raise ValueError("Select who this record is being created for")
                await api.update_record_draft(draft["id"], payload)
                committed_record = await api.commit_record_draft(
                    draft["id"], int(creator_role_id),
                )
                dialog.close()
                ui.notify("Record and digital components created", color="positive")
                await load_recent(spec)
                if on_committed is not None:
                    await on_committed(committed_record)
                    return
                state["searched"] = False
                render_table(spec)
            except ValueError as error:
                ui.notify(str(error), color="warning")
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        with dialog, ui.card().classes("max-h-[calc(100vh-32px)] p-0").style("width: 1050px; max-width: calc(100vw - 32px)"):
            with ui.row().classes("w-full items-center no-wrap px-6 pt-5"):
                ui.avatar(icon="note_add", color="blue-1", text_color="primary")
                with ui.column().classes("gap-0 grow"):
                    ui.label("Create record").classes("text-xl font-semibold")
                    ui.label("Assemble the metadata and files, then create them as one record package.").classes("text-sm text-slate-500")
                ui.badge("Draft", color="primary").props("outline")
            with ui.element("div").classes("w-full overflow-y-auto px-6 pb-2 max-h-[calc(100vh-190px)]"):
                ui.label("Record details").classes("text-base font-semibold mt-4 mb-2")
                ui.label("* Required fields").classes("text-xs text-slate-500 -mt-1 mb-2")
                with ui.grid(columns=2).classes("w-full gap-3"):
                    aggregation_field = next(
                        field for field in spec.fields if field.name == "aggregation_id"
                    )
                    controls["aggregation_id"] = field_input(
                        aggregation_field,
                        value=target_aggregation_id,
                        options=relationship_options(
                            aggregations, aggregation_field.lookup_label_fields,
                        ),
                    )
                    controls["aggregation_id"].classes("col-span-2")
                    if target_aggregation_id is not None:
                        controls["aggregation_id"].disable()

                    role_options = {
                        item["role_id"]: item["label"] for item in creation_roles
                    } if target_aggregation_id is not None else {}
                    controls["creator_acl_role_id"] = ui.select(
                        role_options,
                        value=(
                            creation_roles[0]["role_id"]
                            if target_aggregation_id is not None and len(creation_roles) == 1
                            else None
                        ),
                        label="Create for *",
                    ).props("outlined options-dense").classes("w-full col-span-2")
                    if target_aggregation_id is None or len(creation_roles) <= 1:
                        controls["creator_acl_role_id"].disable()
                    ui.label(
                        "Select the role that will receive creator access. The record belongs to the "
                        "parent aggregation's organizational unit."
                    ).classes("text-xs leading-5 text-slate-500 col-span-2 -mt-2")
                    creation_role_status = ui.label(
                        "Select a parent aggregation before choosing Create for."
                        if target_aggregation_id is None
                        else (
                            "Create for was set automatically because you have one eligible role."
                            if len(creation_roles) == 1
                            else (
                                "You do not have an effective role in the parent aggregation's "
                                "organizational unit, so you cannot create a record there."
                                if not creation_roles
                                else "Choose one of your roles in the parent aggregation's organizational unit."
                            )
                        )
                    ).props('role="status" aria-live="polite"').classes(
                        "text-xs leading-5 text-amber-800 col-span-2 -mt-2"
                    )
                    for field in spec.fields:
                        if field.name == "aggregation_id":
                            continue
                        lookup_rows = (
                            aggregations if field.lookup_resource == "aggregations"
                            else security_levels if field.lookup_resource == "security-levels"
                            else []
                        )
                        options = relationship_options(lookup_rows, field.lookup_label_fields) if field.lookup_resource else None
                        initial_value = None
                        if field.name == "security_level_id" and security_levels:
                            initial_value = min(
                                security_levels, key=lambda item: (item["level_number"], item["id"])
                            )["id"]
                        controls[field.name] = field_input(field, value=initial_value, options=options)
                        if field.kind == "textarea":
                            controls[field.name].classes("col-span-2")
                    def constrain_record_security_levels() -> None:
                        aggregation = aggregations_by_id.get(controls["aggregation_id"].value)
                        if not aggregation:
                            return
                        parent_level = next(
                            (item for item in security_levels if item["id"] == aggregation.get("security_level_id")),
                            None,
                        )
                        if not parent_level:
                            return
                        allowed = [
                            item for item in security_levels
                            if item["level_number"] <= parent_level["level_number"]
                        ]
                        controls["security_level_id"].options = relationship_options(
                            allowed, ("code", "name")
                        )
                        controls["security_level_id"].update()
                    controls["aggregation_id"].on_value_change(
                        lambda _: constrain_record_security_levels()
                    )
                    async def refresh_record_creation_roles() -> None:
                        aggregation_id = controls["aggregation_id"].value
                        role_control = controls["creator_acl_role_id"]
                        previous_role_id = role_control.value
                        if aggregation_id is None:
                            role_control.set_options({}, value=None)
                            role_control.disable()
                            creation_role_status.set_text(
                                "Select a parent aggregation before choosing Create for."
                            )
                            return
                        try:
                            rows = await api.creation_role_options(int(aggregation_id))
                        except ApiError as error:
                            ui.notify(error_message(error), color="negative", close_button=True)
                            return
                        eligible_role_ids = {item["role_id"] for item in rows}
                        previous_role_was_cleared = (
                            previous_role_id is not None
                            and previous_role_id not in eligible_role_ids
                        )
                        selected_role_id = (
                            previous_role_id if previous_role_id in eligible_role_ids
                            else rows[0]["role_id"] if len(rows) == 1
                            else None
                        )
                        role_control.set_options(
                            {item["role_id"]: item["label"] for item in rows},
                            value=selected_role_id,
                        )
                        if len(rows) <= 1:
                            role_control.disable()
                        else:
                            role_control.enable()
                        if not rows:
                            creation_role_status.set_text(
                                "You do not have an effective role in the parent aggregation's "
                                "organizational unit, so you cannot create a record there."
                            )
                        elif previous_role_was_cleared:
                            creation_role_status.set_text(
                                "Your previous Create for selection was cleared because it does not "
                                "belong to the parent aggregation's organizational unit."
                            )
                        elif len(rows) == 1:
                            creation_role_status.set_text(
                                "Create for was set automatically because you have one eligible role."
                            )
                        else:
                            creation_role_status.set_text(
                                "Choose one of your roles in the parent aggregation's organizational unit."
                            )

                    controls["aggregation_id"].on_value_change(
                        lambda _: refresh_record_creation_roles()
                    )
                    constrain_record_security_levels()
                with ui.row().classes("w-full items-center mt-5 mb-2"):
                    with ui.column().classes("gap-0"):
                        ui.label("Digital components").classes("text-base font-semibold")
                        ui.label("Files remain staged until you create the record.").classes("text-xs text-slate-500")
                uploader_control["uploader"] = component_uploader(upload_to_draft)
                with ui.element("div").classes("component-list w-full mt-3") as component_list:
                    component_area = ui.element("div").classes("component-grid w-full")
                component_list.set_visibility(False)
            ui.separator()
            with ui.row().classes("w-full justify-end gap-2 px-6 py-4"):
                with ui.row().classes(
                    "items-center gap-1 text-sm text-slate-500 mr-2"
                ) as upload_wait:
                    ui.icon("hourglass_top", size="18px")
                    ui.label(RECORD_UPLOAD_WAIT_MESSAGE)
                upload_wait.set_visibility(False)
                action_controls["upload_wait"] = upload_wait
                ui.button("Cancel draft", on_click=discard).props("flat color=grey-7")
                action_controls["commit"] = ui.button("Create record", icon="check", on_click=commit).props("unelevated")
        dialog.open()
        await refresh_draft_components()

    async def open_editor(
        row: dict[str, Any] | None = None, on_saved=None,
        initial_values: dict[str, Any] | None = None,
        locked_fields: set[str] | None = None,
        resource_key: str | None = None,
    ) -> None:
        resolved_resource = resource_key or {
            "aggregation-details": "aggregations",
            "record-details": "records",
            "org-unit-details": "org-units",
            "role-details": "roles",
            "user-details": "users",
        }.get(state["resource"], state["resource"])
        spec = ENTITIES[resolved_resource]
        creating = row is None
        effective_locked_fields = set(locked_fields or set())
        if row and spec.key in {"aggregations", "records"} and row.get("_effectively_closed"):
            ui.notify(
                f"Closed {spec.singular} metadata cannot be changed",
                color="warning",
            )
            return
        if row and spec.key == "aggregations" and row.get("date_closed") is None:
            try:
                editor_capabilities = await api.resource_capabilities(
                    "aggregations", row["id"]
                )
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
                return
            if not editor_capabilities.get("close"):
                effective_locked_fields.add("date_closed")
        if creating and spec.key == "records":
            await open_record_draft_editor()
            return
        lookup_options: dict[str, dict[int, str]] = {}
        lookup_rows_by_field: dict[str, list[dict[str, Any]]] = {}
        creation_roles: list[dict[str, Any]] = []
        retention_rule: dict[str, Any] | None = None
        try:
            if creating and spec.key == "aggregations":
                creation_roles = await api.creation_role_options(
                    (initial_values or {}).get("parent_aggregation_id")
                )
            if row and spec.key == "classifications":
                try:
                    retention_rule = await api.classification_retention_rule(row["id"])
                except ApiError as error:
                    if error.status_code != 404:
                        raise
            for field in spec.fields:
                if not field.lookup_resource:
                    continue
                lookup_rows = (
                    await api.profile_references()
                    if field.lookup_resource == "profiles"
                    else await api.list(
                        field.lookup_resource,
                        **({"eligible": True} if field.kind == "classification" else {}),
                    )
                )
                if row and field.lookup_resource == spec.key:
                    lookup_rows = [item for item in lookup_rows if item["id"] != row["id"]]
                lookup_rows_by_field[field.name] = lookup_rows
                if field.kind == "classification":
                    hierarchy_rows = await api.list("classifications")
                    recent = await api.recent_classifications(
                        classification_recent_selection_limit()
                    )
                    recent_ids = {item["id"] for item in recent}
                    by_id = {item["id"]: item for item in hierarchy_rows}
                    def classification_depth(item: dict[str, Any]) -> int:
                        depth, parent_id, seen = 0, item.get("parent_classification_id"), set()
                        while parent_id in by_id and parent_id not in seen:
                            seen.add(parent_id); depth += 1
                            parent_id = by_id[parent_id].get("parent_classification_id")
                        return depth
                    lookup_rows.sort(key=lambda item: (
                        item["id"] not in recent_ids,
                        classification_depth(item), item.get("code", ""),
                    ))
                    lookup_options[field.name] = {
                        item["id"]: (
                            ("★ Recent · " if item["id"] in recent_ids else "")
                            + ("› " * classification_depth(item))
                            + " · ".join(filter(None, (
                                item.get(field_name)
                                for field_name in CLASSIFICATION_SELECTOR_SEARCH_FIELDS
                            )))
                        ) for item in lookup_rows
                    }
                else:
                    lookup_options[field.name] = relationship_options(
                        lookup_rows, field.lookup_label_fields
                    )
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return

        async def browse_classification_tree(target_control: Any) -> None:
            browser = ui.dialog()
            content: Any = None

            async def show_schemes() -> None:
                try:
                    schemes = await api.list("classification-schemes", eligible=True)
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)
                    return
                content.clear()
                with content:
                    ui.label("Published classification schemes").classes("text-lg font-semibold")
                    ui.label("Choose a scheme to browse its classification hierarchy.").classes("text-sm text-slate-500")
                    if not schemes:
                        ui.label("No active published classification schemes are available.").classes("py-8 text-slate-400")
                    for scheme in schemes:
                        with ui.card().classes("w-full shadow-none border border-slate-200 cursor-pointer").on(
                            "click", lambda _, selected=scheme: show_level(selected, None, [])
                        ):
                            with ui.row().classes("w-full items-start gap-3 no-wrap"):
                                ui.avatar(
                                    icon="account_tree", color="blue-1", text_color="primary"
                                ).classes("shrink-0")
                                with ui.column().classes("gap-0 grow min-w-0"):
                                    ui.label(scheme["title"]).classes(
                                        "w-full font-semibold whitespace-normal break-words"
                                    )
                                    ui.label(scheme["code"]).classes(
                                        "w-full text-xs text-primary truncate"
                                    )
                                    if scheme.get("description"):
                                        ui.label(scheme["description"]).classes(
                                            "w-full text-xs text-slate-500 line-clamp-2"
                                        )
                                ui.icon("chevron_right").classes(
                                    "text-slate-400 shrink-0 self-center"
                                )

            async def show_level(
                scheme: dict[str, Any], parent: dict[str, Any] | None,
                path: list[dict[str, Any]],
            ) -> None:
                try:
                    rows = await api.list(
                        "classifications",
                        classification_scheme_id=scheme["id"],
                        **({"roots_only": True} if parent is None else {"parent_classification_id": parent["id"]}),
                    )
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)
                    return
                content.clear()
                with content:
                    with ui.row().classes("w-full items-center gap-1"):
                        ui.button(icon="arrow_back", on_click=show_schemes if not path else lambda: show_level(scheme, path[-1] if path else None, path[:-1])).props("flat round dense").tooltip("Back")
                        ui.label(scheme["title"]).classes("font-semibold")
                        for ancestor in path:
                            ui.icon("chevron_right", size="16px").classes("text-slate-400")
                            ui.label(ancestor["code"]).classes("text-xs text-slate-500")
                        if parent:
                            ui.icon("chevron_right", size="16px").classes("text-slate-400")
                            ui.label(parent["code"]).classes("text-xs font-semibold text-primary")
                    if not rows:
                        ui.label("This branch has no child classifications yet.").classes("py-8 text-slate-400")
                    for classification in rows:
                        async def choose(item=classification) -> None:
                            if item["is_terminal"]:
                                target_control.value = item["id"]
                                target_control.update()
                                browser.close()
                            else:
                                await show_level(
                                    scheme, item,
                                    [*path, parent] if parent else path,
                                )
                        with ui.card().classes("w-full shadow-none border border-slate-200 cursor-pointer").on("click", choose):
                            with ui.row().classes("w-full items-center gap-3"):
                                ui.avatar(
                                    icon="label" if classification["is_terminal"] else "schema",
                                    color="blue-1", text_color="primary",
                                )
                                with ui.column().classes("gap-0 grow"):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.label(classification["title"]).classes("font-semibold")
                                        ui.badge(
                                            "Terminal" if classification["is_terminal"] else "Branch",
                                            color="primary",
                                        ).props("outline")
                                    ui.label(classification["code"]).classes("text-xs text-primary")
                                    if classification.get("description"):
                                        ui.label(classification["description"]).classes("text-xs text-slate-500 line-clamp-2")
                                ui.icon("check_circle" if classification["is_terminal"] else "chevron_right", color="primary")

            with browser, ui.card().classes("w-[760px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)]"):
                with ui.row().classes("w-full items-center"):
                    ui.label("Browse classifications").classes("text-xl font-semibold")
                    ui.space()
                    ui.button(icon="close", on_click=browser.close).props("flat round")
                content = ui.column().classes("w-full gap-2 overflow-y-auto max-h-[calc(100vh-150px)]")
            browser.open()
            await show_schemes()

        dialog = ui.dialog()
        controls: dict[str, Any] = {}
        with dialog, ui.card().classes("w-[620px] max-w-full"):
            ui.label(f"{'Add' if creating else 'Edit'} {spec.singular}").classes("text-xl font-semibold")
            ui.label("* Required fields").classes("text-xs text-slate-500 -mt-2")
            with ui.column().classes("w-full gap-3"):
                if not creating and spec.key in {"aggregations", "records"}:
                    owner_label = " — ".join(filter(None, (
                        row.get("owning_org_unit_code"),
                        row.get("owning_org_unit_name"),
                    ))) or "Unavailable"
                    ui.input(
                        "Owning organizational unit", value=owner_label,
                    ).props("outlined readonly").classes("w-full")
                    ui.label(
                        "Ownership is determined by placement. Move the resource through the governed move action to change it."
                    ).classes("text-xs leading-5 text-slate-500 -mt-2")
                if creating and spec.key == "aggregations":
                    parent_field = next(
                        field for field in spec.fields if field.name == "parent_aggregation_id"
                    )
                    initial_parent_id = (initial_values or {}).get("parent_aggregation_id")
                    controls["parent_aggregation_id"] = field_input(
                        parent_field,
                        initial_parent_id,
                        lookup_options.get("parent_aggregation_id"),
                    )
                    ui.label(
                        "Optional. Leave this blank to create a root aggregation; select a parent "
                        "to create a child aggregation beneath it."
                    ).classes("text-xs leading-5 text-slate-500 -mt-2")
                    if "parent_aggregation_id" in effective_locked_fields:
                        controls["parent_aggregation_id"].disable()
                    role_options = {
                        item["role_id"]: item["label"] for item in creation_roles
                    }
                    initial_role_id = (
                        creation_roles[0]["role_id"] if len(creation_roles) == 1 else None
                    )
                    controls["creator_acl_role_id"] = ui.select(
                        role_options, value=initial_role_id, label="Create for *",
                    ).props("outlined options-dense").classes("w-full")
                    if len(creation_roles) == 1:
                        controls["creator_acl_role_id"].disable()
                    ui.label(
                        "For a child aggregation, the parent determines the owning organizational unit "
                        "and Create for selects the role that receives creator access. For a root "
                        "aggregation, Create for determines both."
                    ).classes("text-xs leading-5 text-slate-500 -mt-2")
                    aggregation_creation_role_status = ui.label(
                        (
                            (
                                "You do not have an eligible role in the parent aggregation's "
                                "organizational unit, so you cannot add a child aggregation there."
                                if initial_parent_id is not None
                                else "You do not have an eligible role, so you cannot create a root aggregation."
                            )
                            if not creation_roles
                            else "Choose one of your roles in the parent aggregation's organizational unit."
                            if initial_parent_id is not None and len(creation_roles) > 1
                            else "Create for was set automatically because you have one eligible role."
                            if initial_parent_id is not None
                            else "No parent is selected, so this will be a root aggregation and the "
                            "selected role's organizational unit will become its owner."
                        )
                    ).props('role="status" aria-live="polite"').classes(
                        "text-xs leading-5 text-amber-800 -mt-2"
                    )
                for field in spec.fields:
                    if creating and spec.key == "aggregations" and field.name == "parent_aggregation_id":
                        continue
                    source = retention_rule if field.name in {
                        "current_period_years", "intermediate_period_years",
                        "final_disposition", "instructions",
                    } else row
                    initial_value = (
                        (initial_values or {}).get(field.name)
                        if creating else source.get(field.name) if source else None
                    )
                    if creating and field.name == "security_level_id" and initial_value is None:
                        available_levels = lookup_rows_by_field.get(field.name, [])
                        if spec.key == "aggregations" and (initial_values or {}).get("parent_aggregation_id"):
                            parent = next(
                                (item for item in lookup_rows_by_field.get("parent_aggregation_id", [])
                                 if item["id"] == (initial_values or {}).get("parent_aggregation_id")),
                                None,
                            )
                            initial_value = parent.get("security_level_id") if parent else None
                        if initial_value is None and available_levels:
                            initial_value = min(
                                available_levels, key=lambda item: (item["level_number"], item["id"])
                            )["id"]
                    if creating and field.name == "profile_id" and initial_value is None:
                        available_profiles = lookup_rows_by_field.get(field.name, [])
                        compatibility = next(
                            (item for item in available_profiles if item.get("code") == "ALL_PRIVS"),
                            None,
                        )
                        initial_value = compatibility["id"] if compatibility else None
                    controls[field.name] = field_input(
                        field,
                        initial_value,
                        lookup_options.get(field.name),
                    )
                    if spec.key == "roles" and field.name == "profile_id":
                        profiles_by_id = {
                            item["id"]: item
                            for item in lookup_rows_by_field.get(field.name, [])
                        }
                        with ui.row().classes(
                            "w-full items-start gap-2 rounded-lg border border-amber-200 "
                            "bg-amber-50 px-3 py-2 -mt-2"
                        ) as all_privileges_warning:
                            ui.icon("warning_amber", color="amber-9", size="20px").classes(
                                "mt-0.5 shrink-0"
                            )
                            ui.label(
                                "This profile grants every currently defined system privilege. "
                                "A role with it has unrestricted system capabilities, subject to "
                                "security clearance and resource ACL checks. Use a purpose-specific "
                                "profile before production. This warning does not prevent saving."
                            ).classes("text-xs leading-5 text-amber-10")

                        def update_all_privileges_warning() -> None:
                            all_privileges_warning.set_visibility(
                                bool(
                                    profiles_by_id.get(controls["profile_id"].value, {}).get(
                                        "grants_all_privileges"
                                    )
                                )
                            )

                        controls["profile_id"].on_value_change(
                            lambda _: update_all_privileges_warning()
                        )
                        update_all_privileges_warning()
                    if field.lookup_resource in {"org-units", "roles", "users"}:
                        selector_mode = {
                            "org-units": "org_unit", "roles": "role", "users": "user",
                        }[field.lookup_resource]
                        ui.button(
                            "Browse organization structure", icon="account_tree",
                            on_click=lambda _, control=controls[field.name], mode=selector_mode: show_organization_structure(
                                selection_mode=mode, target_control=control,
                            ),
                        ).props("flat dense no-caps color=primary").classes("self-start -mt-2")
                    if field.name in effective_locked_fields:
                        controls[field.name].disable()
                        if spec.key == "aggregations" and field.name == "date_closed":
                            ui.label(
                                "Closing an aggregation requires the aggregation.close privilege."
                            ).classes("text-xs leading-5 text-slate-500 -mt-2")
                    if spec.key == "profiles" and field.name == "code" and not creating:
                        controls[field.name].disable()
                    if spec.key == "roles" and field.name == "is_information_governance":
                        ui.label(
                            "Information-governance roles may bypass resource ACLs for governed content. "
                            "They still require global privileges, sufficient clearance, effective assignments, "
                            "and compliance with every other integrity control."
                        ).classes("text-xs leading-5 text-slate-500 -mt-2")
                    if (
                        spec.key == "classification-schemes"
                        and field.name == "date_published"
                        and not creating
                    ):
                        controls[field.name].disable()
                        ui.label(
                            "Use the Publish or Unpublish action to change publication status."
                        ).classes("text-xs text-slate-500 -mt-2")
                    if spec.key == "aggregations" and field.name == "classification_id":
                        parent_id = (initial_values or {}).get("parent_aggregation_id") if creating else row.get("parent_aggregation_id")
                        if parent_id is not None:
                            controls[field.name].value = None
                            controls[field.name].disable()
                            with ui.row().classes(
                                "w-full items-start gap-1 text-xs text-slate-500 -mt-2"
                            ):
                                ui.icon("info", size="16px").classes("mt-px shrink-0")
                                ui.label(CHILD_AGGREGATION_CLASSIFICATION_HELP).classes(
                                    "leading-5"
                                )
                        else:
                            ui.button(
                                "Browse classification tree", icon="account_tree",
                                on_click=lambda control=controls[field.name]: browse_classification_tree(control),
                            ).props("outline dense no-caps color=primary").classes("self-start")

            if spec.key == "aggregations" and "security_level_id" in controls:
                all_levels = lookup_rows_by_field.get("security_level_id", [])
                parents = lookup_rows_by_field.get("parent_aggregation_id", [])

                def constrain_aggregation_security_levels() -> None:
                    parent_control = controls.get("parent_aggregation_id")
                    parent_id = parent_control.value if parent_control else None
                    parent = next((item for item in parents if item["id"] == parent_id), None)
                    maximum = next(
                        (item["level_number"] for item in all_levels
                         if parent and item["id"] == parent.get("security_level_id")),
                        None,
                    )
                    permitted = [
                        item for item in all_levels
                        if maximum is None or item["level_number"] <= maximum
                    ]
                    security_control = controls["security_level_id"]
                    security_field = next(
                        field for field in spec.fields if field.name == "security_level_id"
                    )
                    security_control.options = relationship_options(
                        permitted, security_field.lookup_label_fields
                    )
                    if security_control.value not in security_control.options:
                        security_control.value = parent.get("security_level_id") if parent else (
                            min(permitted, key=lambda item: (item["level_number"], item["id"]))["id"]
                            if permitted else None
                        )
                    security_control.update()

                if controls.get("parent_aggregation_id"):
                    controls["parent_aggregation_id"].on_value_change(
                        lambda _: constrain_aggregation_security_levels()
                    )
                    if creating:
                        async def refresh_aggregation_creation_roles() -> None:
                            control = controls["creator_acl_role_id"]
                            previous_role_id = control.value
                            parent_id = controls["parent_aggregation_id"].value
                            try:
                                rows = await api.creation_role_options(
                                    parent_id
                                )
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)
                                return
                            options = {item["role_id"]: item["label"] for item in rows}
                            eligible_role_ids = set(options)
                            previous_role_was_cleared = (
                                previous_role_id is not None
                                and previous_role_id not in eligible_role_ids
                            )
                            selected_role_id = (
                                previous_role_id if previous_role_id in eligible_role_ids
                                else rows[0]["role_id"] if len(rows) == 1
                                else None
                            )
                            control.set_options(
                                options,
                                value=selected_role_id,
                            )
                            if len(rows) <= 1:
                                control.disable()
                            else:
                                control.enable()
                            if not rows:
                                aggregation_creation_role_status.set_text(
                                    "You do not have an eligible role"
                                    + (
                                        " in the parent aggregation's organizational unit, so you "
                                        "cannot add a child aggregation there."
                                        if parent_id is not None
                                        else ", so you cannot create a root aggregation."
                                    )
                                )
                            elif previous_role_was_cleared:
                                aggregation_creation_role_status.set_text(
                                    "Your previous Create for selection was cleared because it does not "
                                    "belong to the parent aggregation's organizational unit."
                                )
                            elif parent_id is None:
                                aggregation_creation_role_status.set_text(
                                    "No parent is selected, so this will be a root aggregation and the "
                                    "selected role's organizational unit will become its owner."
                                )
                            elif len(rows) == 1:
                                aggregation_creation_role_status.set_text(
                                    "Create for was set automatically because you have one eligible role."
                                )
                            else:
                                aggregation_creation_role_status.set_text(
                                    "Choose one of your roles in the parent aggregation's organizational unit."
                                )

                        controls["parent_aggregation_id"].on_value_change(
                            lambda _: refresh_aggregation_creation_roles()
                        )
                constrain_aggregation_security_levels()

            security_change_reason = None
            if not creating and spec.key in {"aggregations", "records", "roles"}:
                security_change_reason = ui.textarea(
                    "Reason for sensitive authorization changes" if spec.key == "roles" else "Reason for lowering the security level",
                    placeholder=(
                        "Required for profile, governance-status, or clearance reductions"
                        if spec.key == "roles" else "Required only when selecting a lower level"
                    ),
                ).props("outlined autogrow").classes("w-full")
            profile_change_reason = None
            if not creating and spec.key == "profiles":
                profile_change_reason = ui.textarea(
                    "Reason for changing this profile", placeholder="Required",
                ).props("outlined autogrow").classes("w-full")

            async def save() -> None:
                try:
                    payload = form_payload(spec, controls, creating=creating)
                    if creating and spec.key == "aggregations":
                        creator_role_id = controls["creator_acl_role_id"].value
                        if creator_role_id is None:
                            raise ValueError("Select who this aggregation is being created for")
                        payload["creator_acl_role_id"] = int(creator_role_id)
                    if spec.key == "aggregations":
                        if payload.get("parent_aggregation_id") is None and payload.get("classification_id") is None:
                            raise ValueError("A root aggregation must have a terminal classification")
                    rule_payload = None
                    if spec.key == "classifications":
                        rule_values = {
                            key: payload.pop(key, None) for key in (
                                "current_period_years", "intermediate_period_years",
                                "final_disposition", "instructions",
                            )
                        }
                        if any(value not in (None, "") for value in rule_values.values()):
                            required = ("current_period_years", "intermediate_period_years", "final_disposition")
                            if any(rule_values[key] in (None, "") for key in required):
                                raise ValueError("A direct retention rule requires both periods and a final disposition")
                            rule_payload = rule_values
                            if creating:
                                payload["retention_rule"] = rule_payload
                        if not creating:
                            payload.pop("classification_scheme_id", None)
                    if creating:
                        saved = await api.create(spec.key, payload)
                    else:
                        if spec.key == "profiles":
                            payload.pop("code", None)
                        change_reason = None
                        if security_change_reason is not None and "security_level_id" in payload:
                            levels = lookup_rows_by_field.get("security_level_id", [])
                            level_numbers = {item["id"]: item["level_number"] for item in levels}
                            old_number = level_numbers.get(row.get("security_level_id"))
                            new_number = level_numbers.get(payload.get("security_level_id"))
                            if old_number is not None and new_number is not None and new_number < old_number:
                                change_reason = (security_change_reason.value or "").strip()
                                if not change_reason:
                                    raise ValueError("A reason is required when lowering the security level")
                        if spec.key == "roles" and any(
                            payload.get(name) != row.get(name)
                            for name in ("profile_id", "is_information_governance")
                            if name in payload
                        ):
                            change_reason = (security_change_reason.value or "").strip()
                            if not change_reason:
                                raise ValueError(
                                    "A reason is required when changing a role's profile or governance status"
                                )
                        if profile_change_reason is not None:
                            change_reason = (profile_change_reason.value or "").strip()
                            if not change_reason:
                                raise ValueError("A reason is required when changing a profile")
                        saved = await api.update(
                            spec.key, row["id"], row["version"], payload,
                            change_reason=change_reason,
                        )
                        if spec.key == "classifications" and rule_payload is not None:
                            await api.put_classification_retention_rule(
                                row["id"], rule_payload,
                                retention_rule.get("version") if retention_rule else None,
                            )
                    dialog.close()
                    ui.notify(f"{spec.singular.capitalize()} saved", color="positive")
                    if on_saved is not None:
                        if spec.search_first:
                            await load_recent(spec)
                        await on_saved(saved)
                        return
                    if spec.search_first:
                        await load_recent(spec)
                        query = (search_input.value or "").strip()
                        if query:
                            await load_rows(repeat_search=True)
                        else:
                            state["searched"] = False
                            render_table(spec)
                    else:
                        if creating:
                            state["rows"] = [*state["rows"], saved]
                        else:
                            state["rows"] = [
                                saved if item["id"] == saved["id"] else item
                                for item in state["rows"]
                            ]
                        state["rows"].sort(key=lambda item: item["id"])
                        state["rows"] = await decorate_for_spec(spec, state["rows"])
                        render_table(spec)
                except ValueError as error:
                    ui.notify(str(error), color="warning")
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save", on_click=save, icon="save").props("unelevated")
        dialog.open()

    async def show_memberships(entity: dict[str, Any], *, for_user: bool) -> None:
        dialog = ui.dialog()
        entity_kind = "user" if for_user else "role"
        counterpart_resource = "roles" if for_user else "users"
        counterpart_label = "role" if for_user else "user"
        assignment_allowed = (
            entity.get("effective_status", entity.get("status", "active")) == "active"
        )
        assignments_area: Any = None
        selection_holder: dict[str, Any] = {}

        async def load_memberships() -> None:
            try:
                assignments = (
                    await api.user_roles(entity["id"])
                    if for_user else await api.role_users(entity["id"])
                )
                all_counterparts = await api.list(counterpart_resource)
                counterparts = all_counterparts
                units_by_id: dict[int, dict[str, Any]] = {}
                if for_user:
                    units = await api.list("org-units")
                    units_by_id = {item["id"]: item for item in units}
                    counterparts = [
                        item for item in counterparts
                        if item.get("status") == "active"
                        and inactive_org_unit_source(
                            units_by_id.get(item.get("org_unit_id")), units_by_id
                        ) is None
                    ]
                else:
                    counterparts = [
                        item for item in counterparts if item.get("status") == "active"
                    ]
                counterpart_by_id = {item["id"]: item for item in all_counterparts}
                assigned_ids = {
                    item["role_id" if for_user else "user_id"] for item in assignments
                }
                available = [item for item in counterparts if item["id"] not in assigned_ids]
                options = relationship_options(
                    available, ("code", "name") if for_user else ("name",)
                )
                selection_holder["control"].options = options
                selection_holder["control"].value = None
                selection_holder["control"].update()
                assignments_area.clear()
                with assignments_area:
                    if not assignments:
                        ui.label(f"No {counterpart_label}s assigned.").classes("text-slate-500 py-4")
                    else:
                        rows = []
                        for assignment in assignments:
                            counterpart_id = assignment["role_id" if for_user else "user_id"]
                            counterpart = counterpart_by_id.get(counterpart_id, {})
                            inactive_reason = ""
                            effective_status = counterpart.get("status", "inactive")
                            if for_user:
                                if counterpart.get("status") != "active":
                                    effective_status = "inactive"
                                    inactive_reason = "This role is directly inactive."
                                else:
                                    inactive_unit = inactive_org_unit_source(
                                        units_by_id.get(counterpart.get("org_unit_id")),
                                        units_by_id,
                                    )
                                    if inactive_unit:
                                        effective_status = "inactive"
                                        inactive_reason = (
                                            "Ineffective because organizational unit "
                                            f"{inactive_unit.get('code', '')} — "
                                            f"{inactive_unit.get('name', inactive_unit['id'])} is inactive."
                                        )
                                    else:
                                        effective_status = "active"
                                        inactive_reason = "This role is effective."
                            elif effective_status == "active":
                                inactive_reason = "This user is active."
                            elif effective_status == "suspended":
                                inactive_reason = "This user is suspended."
                            else:
                                inactive_reason = "This user is inactive."
                            rows.append({
                                **assignment,
                                "counterpart": (
                                    f"{counterpart.get('code', '')} — {counterpart.get('name', counterpart_id)}"
                                    if for_user else counterpart.get("name", counterpart_id)
                                ),
                                "counterpart_name": counterpart.get("name", str(counterpart_id)),
                                "counterpart_email": counterpart.get("email") or "",
                                "counterpart_avatar": user_avatar(counterpart) if not for_user else None,
                                "counterpart_search": " ".join(
                                    str(value) for value in (
                                        counterpart.get("code"), counterpart.get("name"),
                                        counterpart.get("email"),
                                    ) if value
                                ),
                                "counterpart_status": effective_status,
                                "counterpart_status_reason": inactive_reason,
                            })
                        filter_panel: Any = None

                        def toggle_filter_panel() -> None:
                            filter_panel.set_visibility(not filter_panel.visible)

                        with ui.row().classes("w-full items-center gap-2"):
                            membership_search = ui.input(
                                f"Search {counterpart_label} name"
                                + (" or email" if not for_user else " or code"),
                            ).props("outlined dense clearable debounce=250").classes(
                                "grow max-w-[430px] min-w-[220px]"
                            )
                            ui.button(
                                "Filters", icon="filter_list", on_click=toggle_filter_panel,
                            ).props("flat dense no-caps color=primary").tooltip(
                                "Filter by status or assignment validity"
                            )
                        filter_panel = ui.row().classes(
                            "w-full items-end gap-2 flex-nowrap overflow-x-auto rounded-lg "
                            "bg-slate-50 border border-slate-200 p-3"
                        )
                        with filter_panel:
                            status_options = {
                                "all": "All statuses", "active": "Active",
                                "inactive": "Inactive",
                            }
                            if not for_user:
                                status_options["suspended"] = "Suspended"
                            membership_status = ui.select(
                                status_options,
                                value="all", label="Status",
                            ).props("outlined dense options-dense").classes("w-40 shrink-0")
                            membership_valid_from = ui.input(
                                "Valid during or after",
                            ).props("outlined dense type=date clearable").classes("w-40 shrink-0")
                            membership_valid_until = ui.input(
                                "Valid during or before",
                            ).props("outlined dense type=date clearable").classes("w-40 shrink-0")
                            ui.button(
                                icon="filter_alt_off",
                                on_click=lambda: (
                                    membership_status.set_value("all"),
                                    membership_valid_from.set_value(None),
                                    membership_valid_until.set_value(None),
                                ),
                            ).props("flat round dense color=grey-7 aria-label='Clear filters'").tooltip(
                                "Clear filters"
                            )
                        filter_panel.set_visibility(False)
                        membership_table = ui.table(
                            columns=[
                                {"name": "counterpart", "label": counterpart_label.capitalize(), "field": "counterpart", "align": "left", "sortable": True},
                                {"name": "counterpart_status", "label": "Status", "field": "counterpart_status", "align": "left", "sortable": True},
                                {"name": "valid_from", "label": "Valid from", "field": "valid_from", "align": "left", "sortable": True},
                                {"name": "valid_until", "label": "Valid until", "field": "valid_until", "align": "left", "sortable": True},
                                {"name": "actions", "label": "", "field": "actions", "align": "right"},
                            ],
                            rows=rows,
                            row_key="id",
                            pagination={"rowsPerPage": 10, "sortBy": "counterpart", "descending": False},
                        ).props("flat bordered dense").classes("w-full membership-table")

                        if not for_user:
                            membership_table.add_slot(
                                "body-cell-counterpart",
                                '''
                                <q-td :props="props">
                                  <div class="column">
                                    <div class="row items-center no-wrap q-gutter-sm">
                                      <q-avatar size="36px" :style="{ backgroundColor: props.row.counterpart_avatar.color, color: 'white' }">
                                        {{ props.row.counterpart_avatar.initials }}
                                      </q-avatar>
                                      <div class="column">
                                        <span>{{ props.row.counterpart_name }}</span>
                                        <span v-if="props.row.counterpart_email" class="text-caption text-grey-7">{{ props.row.counterpart_email }}</span>
                                      </div>
                                    </div>
                                  </div>
                                </q-td>
                                ''',
                            )

                        def apply_membership_filters() -> None:
                            membership_table.rows = filter_membership_rows(
                                rows,
                                query=membership_search.value or "",
                                status=membership_status.value or "all",
                                valid_from=membership_valid_from.value or None,
                                valid_until=membership_valid_until.value or None,
                            )
                            membership_table.update()

                        for control in (
                            membership_search, membership_status,
                            membership_valid_from, membership_valid_until,
                        ):
                            control.on_value_change(apply_membership_filters)
                        add_timestamp_slots(membership_table, ["valid_from", "valid_until"])
                        membership_table.add_slot(
                            "body-cell-counterpart_status",
                            '''
                            <q-td :props="props">
                              <q-badge
                                :color="props.value === 'active' ? 'positive' : (props.value === 'suspended' ? 'warning' : 'grey-7')"
                                :label="props.value === 'active' ? 'Active' : (props.value === 'suspended' ? 'Suspended' : 'Inactive')"
                              ><q-tooltip>{{ props.row.counterpart_status_reason }}</q-tooltip></q-badge>
                            </q-td>
                            ''',
                        )
                        membership_table.add_slot(
                            "body-cell-actions",
                            '<q-td :props="props"><q-btn flat round dense icon="person_remove" color="negative" @click="$parent.$emit(\'remove\', props.row)"><q-tooltip>Remove assignment</q-tooltip></q-btn></q-td>',
                        )

                        async def remove_assignment(event) -> None:
                            assignment = event.args
                            try:
                                await api.delete_assignment(assignment["id"], assignment["version"])
                                ui.notify("Assignment removed", color="positive")
                                await load_memberships()
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        membership_table.on("remove", remove_assignment)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def assign() -> None:
            counterpart_id = selection_holder["control"].value
            if counterpart_id is None:
                ui.notify(f"Select a {counterpart_label}", color="warning")
                return
            payload = {
                "user_id": entity["id"] if for_user else int(counterpart_id),
                "role_id": int(counterpart_id) if for_user else entity["id"],
            }
            try:
                await api.create("user-role-assignments", payload)
                ui.notify(f"{counterpart_label.capitalize()} assigned", color="positive")
                await load_memberships()
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        with dialog, ui.card().classes(
            "membership-dialog flex flex-col"
        ):
            heading = entity.get("name") or entity.get("code") or entity["id"]
            ui.label(f"{counterpart_label.capitalize()} assignments — {heading}").classes("text-xl font-semibold")
            if not assignment_allowed:
                with ui.row().classes("w-full items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg"):
                    ui.icon("block", color="amber-8")
                    ui.label(
                        "New assignments are unavailable while this user or role is ineffective. Existing assignments remain visible."
                    ).classes("text-sm text-amber-900")
            assignments_area = ui.column().classes("w-full min-h-0 overflow-hidden")
            with ui.row().classes("w-full items-end gap-2"):
                selection_holder["control"] = relationship_select(
                    f"Select {counterpart_label}", {}
                ).classes("grow")
                ui.button(
                    "Browse", icon="account_tree",
                    on_click=lambda: show_organization_structure(
                        selection_mode="role" if for_user else "user",
                        target_control=selection_holder["control"],
                    ),
                ).props("outline no-caps color=primary aria-label='Browse organization structure'").tooltip(
                    f"Browse and select a {counterpart_label}"
                )
                assign_button = ui.button("Assign", on_click=assign, icon="person_add").props("unelevated")
                if not assignment_allowed:
                    selection_holder["control"].disable()
                    assign_button.disable()
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()
        await load_memberships()

    async def open_aggregation(aggregation: dict[str, Any]) -> None:
        register_navigation(
            "aggregation-details", aggregation.get("title") or f"Aggregation #{aggregation['id']}",
            entity_id=aggregation["id"],
            accessible_label=" — ".join(filter(None, (
                aggregation.get("title"), aggregation.get("aggregation_number"),
            ))),
        )
        previous_resource = state.get("resource")
        if previous_resource != "aggregation-details":
            state["aggregation_detail_return_resource"] = previous_resource
            state["aggregation_detail_return_record_id"] = state.get("record_detail_id")
        state["resource"] = "aggregation-details"
        try:
            all_aggregations = await api.list("aggregations")
            by_id = {item["id"]: item for item in all_aggregations}
            current = by_id.get(aggregation["id"], aggregation)
            security_level = await api.get("security-levels", current["security_level_id"])
            capabilities = await api.resource_capabilities("aggregations", current["id"])
            closure = effective_closure(current, by_id)
            ancestors = []
            seen = {current["id"]}
            parent_id = current.get("parent_aggregation_id")
            while parent_id and parent_id not in seen and parent_id in by_id:
                parent = by_id[parent_id]
                ancestors.append(parent)
                seen.add(parent_id)
                parent_id = parent.get("parent_aggregation_id")
            ancestors.reverse()
            children = [
                item for item in all_aggregations
                if item.get("parent_aggregation_id") == current["id"]
            ]
            records = await api.list("records", aggregation_id=current["id"])
            effective_rule = None
            local_retention_rule = None
            classification_path = []
            try:
                effective_rule = await api.effective_retention_rule(current["id"])
                if current.get("parent_aggregation_id") is None:
                    local_retention_rule = await api.aggregation_retention_rule(current["id"])
                if effective_rule.get("classification_id"):
                    classification_path = await api.classification_path(
                        effective_rule["classification_id"]
                    )
            except ApiError as error:
                if error.status_code != 404:
                    raise
            for record in records:
                record["_effectively_closed"] = closure is not None
            state["aggregation_detail"] = current
            if closure is None and capabilities.get("add_child"):
                add_button.text = "Add child aggregation"
                add_button.update()
                add_button.set_visibility(True)
            else:
                add_button.set_visibility(False)
            if closure is None and capabilities.get("add_record"):
                add_record_button.set_visibility(True)
            else:
                add_record_button.set_visibility(False)
            search_bar.set_visibility(False)
            aggregation_mode_bar.set_visibility(False)
            guidance.text = ""
            title.text = current["title"]
            subtitle.text = current["aggregation_number"]
            table_container.clear()
            with table_container:
                async def leave_aggregation_page() -> None:
                    await breadcrumb_back(lambda: select_entity("aggregations"))

                async def reopen_current() -> None:
                    try:
                        reopened = await api.update(
                            "aggregations", current["id"], current["version"],
                            {"date_closed": None},
                        )
                        ui.notify("Aggregation reopened", color="positive")
                        await load_recent(ENTITIES["aggregations"])
                        await open_aggregation(reopened)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                async def close_current() -> None:
                    try:
                        closed = await api.update(
                            "aggregations", current["id"], current["version"],
                            {"date_closed": datetime.now(timezone.utc).isoformat()},
                        )
                        ui.notify("Aggregation closed", color="positive")
                        await load_recent(ENTITIES["aggregations"])
                        await open_aggregation(closed)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                async def manage_local_retention_rule() -> None:
                    dialog = ui.dialog()
                    existing = local_retention_rule or {}
                    with dialog, ui.card().classes("w-[680px] max-w-full"):
                        ui.label("Local retention override").classes("text-xl font-semibold")
                        ui.label(
                            "This root-only rule overrides the classification rule for the complete aggregation hierarchy."
                        ).classes("text-sm text-slate-500")
                        with ui.grid(columns=2).classes("w-full gap-3"):
                            current_years = ui.number(
                                "Current retention (years)", value=existing.get("current_period_years"),
                                min=0, format="%.0f",
                            ).props("outlined").classes("w-full")
                            intermediate_years = ui.number(
                                "Intermediate retention (years)", value=existing.get("intermediate_period_years"),
                                min=0, format="%.0f",
                            ).props("outlined").classes("w-full")
                        disposition = ui.select({
                            "destruction": "Destruction",
                            "transfer_to_external_archive": "Permanent preservation — external archive",
                            "selective_preservation": "Selective preservation",
                            "retain_as_local_archives": "Retain as local archives",
                        }, label="Final disposition", value=existing.get("final_disposition")).props("outlined").classes("w-full")
                        instructions = ui.textarea(
                            "Retention and disposal instructions", value=existing.get("instructions") or "",
                        ).props("outlined autogrow").classes("w-full")
                        justification = ui.textarea(
                            "Justification", value=existing.get("justification") or "",
                        ).props("outlined autogrow").classes("w-full")

                        async def save_rule() -> None:
                            if current_years.value is None or intermediate_years.value is None or not disposition.value:
                                ui.notify("Both periods and a final disposition are required", color="warning")
                                return
                            if not (justification.value or "").strip():
                                ui.notify("A justification is required", color="warning")
                                return
                            payload = {
                                "current_period_years": int(current_years.value),
                                "intermediate_period_years": int(intermediate_years.value),
                                "final_disposition": disposition.value,
                                "instructions": (instructions.value or "").strip() or None,
                                "justification": justification.value.strip(),
                            }
                            try:
                                await api.put_aggregation_retention_rule(
                                    current["id"], payload, existing.get("version"),
                                )
                                dialog.close()
                                ui.notify("Local retention override saved", color="positive")
                                await open_aggregation(current)
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        async def remove_rule() -> None:
                            reason = (justification.value or "").strip()
                            if not reason:
                                ui.notify("Enter a justification for removing the override", color="warning")
                                return
                            try:
                                await api.delete_aggregation_retention_rule(current["id"], existing["version"], reason)
                                dialog.close()
                                ui.notify("Local retention override removed", color="positive")
                                await open_aggregation(current)
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        with ui.row().classes("w-full justify-end gap-2"):
                            if existing:
                                ui.button("Remove override", icon="delete_outline", color="negative", on_click=remove_rule).props("flat no-caps")
                            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                            ui.button("Save override", icon="save", on_click=save_rule).props("unelevated no-caps")
                    dialog.open()

                async def confirm_delete_current() -> None:
                    confirmation = ui.dialog()
                    with confirmation, ui.card().classes("w-[500px] max-w-full"):
                        ui.label("Delete aggregation?").classes("text-xl font-semibold")
                        ui.label(
                            f"{current['aggregation_number']} — {current['title']} will be permanently deleted."
                        ).classes("text-sm text-slate-700")
                        ui.label(
                            "Only an open, empty aggregation can be deleted. Its immutable event history will be retained."
                        ).classes("text-xs text-slate-500")

                        async def delete_current() -> None:
                            try:
                                await api.delete(
                                    "aggregations", current["id"], current["version"]
                                )
                                confirmation.close()
                                ui.notify("Aggregation deleted", color="positive")
                                await load_recent(ENTITIES["aggregations"])
                                parent = by_id.get(current.get("parent_aggregation_id"))
                                if parent:
                                    await open_aggregation(parent)
                                else:
                                    await select_entity("aggregations")
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=confirmation.close).props("flat no-caps")
                            ui.button(
                                "Delete aggregation", icon="delete_forever", color="negative",
                                on_click=delete_current,
                            ).props("unelevated no-caps")
                    confirmation.open()

                with ui.row().classes("w-full items-center px-5 pt-4 gap-1 text-sm"):
                    ui.button("Aggregations", icon="folder", on_click=lambda: select_entity("aggregations")).props("flat dense no-caps").classes("breadcrumb-link")
                    for ancestor in ancestors:
                        ui.icon("chevron_right").classes("text-slate-400")
                        ui.button(
                            ancestor["title"],
                            on_click=lambda _, item=ancestor: open_aggregation(item),
                        ).props("flat dense no-caps").classes("breadcrumb-link")
                    ui.icon("chevron_right").classes("text-slate-400")
                    ui.label(current["title"]).classes("font-semibold text-slate-800")

                with ui.row().classes("w-full p-5 gap-4 flex-wrap items-stretch"):
                    with ui.card().classes(
                        AGGREGATION_SUMMARY_LAYOUT_CLASSES
                    ):
                        with ui.row().classes("w-full items-center gap-3 no-wrap"):
                            ui.avatar(icon="folder", color="primary", text_color="white")
                            with ui.column().classes("gap-0 grow min-w-0"):
                                ui.label(current["aggregation_number"]).classes("text-xs text-primary font-semibold")
                                ui.label(current["title"]).classes("text-lg font-semibold break-words")
                            favourite_button("aggregations", current["id"])
                            ui.button(
                                "Back", icon="arrow_back", on_click=leave_aggregation_page,
                            ).props("flat dense no-caps")
                        if closure:
                            with ui.row().classes(
                                "w-full items-center gap-3 rounded-xl border border-amber-200 "
                                "bg-amber-50 px-4 py-3"
                            ):
                                ui.icon("lock", color="amber-8").classes("shrink-0")
                                with ui.column().classes("gap-0 grow min-w-0"):
                                    if closure["id"] == current["id"]:
                                        ui.label("Closed directly").classes(
                                            "text-sm font-semibold text-amber-900"
                                        )
                                    else:
                                        ui.label("Closed by an ancestor aggregation").classes(
                                            "text-sm font-semibold text-amber-900"
                                        )
                                        ui.label(
                                            f"{closure['aggregation_number']} — {closure['title']}"
                                        ).classes("text-xs text-amber-800 truncate")
                                    ui.label(
                                        format_timestamp(closure.get("date_closed"))
                                    ).classes("text-xs text-amber-700")
                                if closure["id"] == current["id"] and capabilities.get("reopen"):
                                    ui.button(
                                        "Reopen", icon="lock_open", on_click=reopen_current,
                                    ).props("flat dense no-caps color=primary").tooltip(
                                        "Clear the closure date; all other metadata remains unchanged"
                                    )
                        if current.get("description"):
                            with ui.column().classes("w-full gap-1 rounded-xl bg-slate-50 px-4 py-3"):
                                ui.label("DESCRIPTION").classes("detail-field-label")
                                ui.label(current["description"]).classes("text-sm leading-6 text-slate-600")
                        with ui.grid(columns=2).classes("w-full gap-x-8 gap-y-0"):
                            aggregation_metadata = (
                                ("Status", "Closed" if closure else "Open"),
                                ("Security level", f"{security_level['code']} — {security_level['name']}"),
                                (
                                    "Owning organizational unit",
                                    f"{current['owning_org_unit_code']} — {current['owning_org_unit_name']}",
                                ),
                                ("Date opened", format_timestamp(current.get("date_opened"))),
                                ("Classification", " › ".join(
                                    f"{item['code']} — {item['title']}" for item in classification_path
                                ) if classification_path else "Unclassified"),
                                ("Contains", f"{len(children)} child aggregations · {len(records)} records"),
                            )
                            for label, value in aggregation_metadata:
                                with ui.column().classes("detail-field gap-1"):
                                    ui.label(label).classes("detail-field-label")
                                    if label == "Status":
                                        ui.badge(
                                            str(value), color="amber-8" if closure else "positive",
                                        ).props("outline")
                                    else:
                                        ui.label(str(value or "—")).classes("detail-field-value")
                        with ui.row().classes("w-full justify-end"):
                            if closure is None and capabilities.get("close"):
                                ui.button(
                                    "Close", icon="lock",
                                    on_click=close_current,
                                ).props("flat dense no-caps").tooltip(
                                    "Close this aggregation using the current date and time"
                                )
                            if closure is None and capabilities.get("delete"):
                                delete_button = ui.button(
                                    "Delete", icon="delete_outline", color="negative",
                                    on_click=confirm_delete_current,
                                ).props("flat dense no-caps")
                                if children or records:
                                    delete_button.disable()
                                    delete_button.tooltip(
                                        "Remove or move all child aggregations and records before deleting"
                                    )
                            if closure is None and capabilities.get("modify_metadata"):
                                ui.button(
                                    "Edit metadata", icon="edit",
                                    on_click=lambda: open_editor(
                                        current, on_saved=open_aggregation,
                                        resource_key="aggregations",
                                    ),
                                ).props("flat dense no-caps")
                            ui.button(
                                "Event history", icon="history",
                                on_click=lambda: show_entity_history("aggregations", current),
                            ).props("flat dense no-caps")
                            ui.button(
                                "Why this access?", icon="fact_check",
                                on_click=lambda: show_access_explanation("aggregation", current["id"]),
                            ).props("flat dense no-caps").tooltip(
                                "Explain the authorization decision gate by gate"
                            )
                            if capabilities.get("manage_acl"):
                                ui.button(
                                    "Access", icon="policy",
                                    on_click=lambda: show_acl_editor(
                                        "aggregations", current["id"], on_saved=lambda: open_aggregation(current),
                                    ),
                                ).props("flat dense no-caps")
                        show_aggregation_move = (
                            closure is None
                            and current.get("parent_aggregation_id") is not None
                            and capabilities.get("move")
                        )
                        show_ownership_correction_action = (
                            closure is None and capabilities.get("correct_ownership")
                        )
                        show_acl_defaults = capabilities.get("manage_acl")
                        if (
                            show_aggregation_move
                            or show_ownership_correction_action
                            or show_acl_defaults
                        ):
                            with ui.expansion(
                                "Advanced", caption="Specialist aggregation actions",
                                icon="tune", value=False,
                            ).classes(
                                "w-full border-t border-slate-100"
                            ):
                                with ui.row().classes("w-full justify-end gap-2 pb-2"):
                                    if show_aggregation_move:
                                        ui.button(
                                            "Move", icon="drive_file_move",
                                            on_click=lambda: show_governed_move(
                                                "aggregations", current, open_aggregation,
                                            ),
                                        ).props("flat dense no-caps")
                                    if show_ownership_correction_action:
                                        ui.button(
                                            "Correct ownership", icon="published_with_changes",
                                            on_click=lambda: show_ownership_correction(
                                                current, open_aggregation,
                                            ),
                                        ).props("flat dense no-caps color=negative")
                                    if show_acl_defaults:
                                        ui.button(
                                            "Child defaults", icon="account_tree",
                                        ).props("flat dense no-caps").on(
                                            "click", lambda: show_acl_editor(
                                                "aggregations", current["id"], scope="aggregation"
                                            )
                                        )
                                        ui.button(
                                            "Record defaults", icon="description",
                                        ).props("flat dense no-caps").on(
                                            "click", lambda: show_acl_editor(
                                                "aggregations", current["id"], scope="record"
                                            )
                                        )
                    if effective_rule:
                        with ui.card().classes(
                            "retention-card shadow-none p-5 gap-4 flex-1 min-w-[360px] max-w-[560px]"
                        ):
                            with ui.row().classes("w-full items-start gap-3"):
                                ui.avatar(icon="schedule", color="blue-1", text_color="primary", size="44px")
                                with ui.column().classes("gap-0 grow"):
                                    ui.label("Effective retention rule").classes("text-lg font-semibold text-slate-900")
                                    if effective_rule["rule_source"] == "aggregation":
                                        source_text = "Specified locally for the governing root aggregation"
                                    elif effective_rule.get("inheritance_depth", 0) == 0:
                                        source_text = "Specified by its classification"
                                    else:
                                        source_text = "Inherited from an ancestor classification"
                                    if current.get("parent_aggregation_id") is not None:
                                        governing_root_id = effective_rule["governing_root_aggregation_id"]
                                        governing_root = by_id.get(governing_root_id)
                                        root_reference = (
                                            f"{governing_root['aggregation_number']} — {governing_root['title']}"
                                            if governing_root else f"#{governing_root_id}"
                                        )
                                        source_text += f" · governed by root aggregation {root_reference}"
                                    ui.label(source_text).classes("text-xs text-sky-700")
                                ui.badge("Effective", color="primary").props("outline")
                            with ui.column().classes("w-full gap-0 pl-1"):
                                for stage_label, stage_value, stage_help in (
                                    ("Current (active)", f"{effective_rule['current_period_years']} years", "Kept with the responsible business unit"),
                                    ("Intermediate (semi-active)", f"{effective_rule['intermediate_period_years']} years", "Retained in intermediate storage"),
                                    ("Final disposition", effective_rule["final_disposition"].replace("_", " ").title(), "Action applied when the retention periods are complete"),
                                ):
                                    with ui.row().classes("retention-stage w-full items-stretch gap-3 pb-4"):
                                        with ui.element("div").classes("retention-line"):
                                            ui.element("div").classes("retention-dot")
                                        with ui.column().classes("gap-0 grow min-w-0"):
                                            ui.label(stage_label).classes("retention-stage-label")
                                            ui.label(stage_value).classes("retention-stage-value")
                                            ui.label(stage_help).classes("text-xs text-slate-500")
                            if classification_path:
                                with ui.column().classes("w-full gap-1 border-t border-sky-100 pt-3"):
                                    ui.label("GOVERNING CLASSIFICATION").classes("detail-field-label")
                                    ui.label(" › ".join(
                                        f"{item['code']} — {item['title']}" for item in classification_path
                                    )).classes("text-sm text-slate-600")
                            if effective_rule.get("instructions"):
                                with ui.column().classes("w-full gap-1 rounded-xl bg-white/70 px-4 py-3"):
                                    ui.label("INSTRUCTIONS").classes("detail-field-label")
                                    ui.label(effective_rule["instructions"]).classes("text-sm text-slate-600")
                            if current.get("parent_aggregation_id") is None and closure is None:
                                with ui.row().classes("w-full justify-end"):
                                    ui.button(
                                        "Edit local override" if local_retention_rule else "Set local override",
                                        icon="tune", on_click=manage_local_retention_rule,
                                    ).props("flat dense no-caps color=primary")
                    else:
                        with ui.card().classes(
                            "detail-surface shadow-none p-5 gap-3 flex-1 min-w-[360px] max-w-[560px]"
                        ):
                            with ui.row().classes("items-center gap-3"):
                                ui.avatar(icon="schedule", color="blue-1", text_color="primary", size="44px")
                                with ui.column().classes("gap-0"):
                                    ui.label("Effective retention rule").classes("text-lg font-semibold")
                                    ui.label("No effective retention rule is available.").classes("text-sm text-slate-500")

                if children:
                    ui.label("Contained aggregations").classes("px-5 text-base font-semibold")
                    with ui.grid(columns=3).classes("w-full px-5 pb-4 gap-3"):
                        for child in children:
                            child_closure = effective_closure(child, by_id)
                            with ui.card().classes("recent-card cursor-pointer p-4").on(
                                "click", lambda _, item=child: open_aggregation(item)
                            ):
                                with ui.row().classes("items-center no-wrap gap-3"):
                                    ui.avatar(icon="folder", color="blue-1", text_color="primary")
                                    with ui.column().classes("gap-0"):
                                        ui.label(child["title"]).classes("font-semibold")
                                        ui.label(child["aggregation_number"]).classes("text-xs text-slate-500")
                                    ui.space()
                                    favourite_button("aggregations", child["id"])
                                    if child_closure:
                                        ui.badge("Closed", color="amber-8").props("outline")

                ui.label("Records in this aggregation").classes("px-5 pt-2 text-base font-semibold")
                if not records:
                    ui.label("This aggregation does not contain any records.").classes("px-5 pb-6 text-slate-500")
                else:
                    for row in records:
                        row["_is_favourite"] = favourite_state("records", row["id"])
                    with ui.row().classes("w-full items-center px-5 pt-2 gap-3"):
                        contained_record_filter = ui.input(
                            "Filter records",
                            placeholder="Number, title, or date",
                        ).props("outlined dense clearable debounce=250").classes("w-80 max-w-full")
                        ui.space()
                        ui.label(f"{len(records)} records").classes("text-sm text-slate-500")
                    record_table = ui.table(
                        columns=[
                            {"name": "record_number", "label": "Number", "field": "record_number", "align": "left", "sortable": True},
                            {"name": "title", "label": "Title", "field": "title", "align": "left", "sortable": True},
                            {"name": "date_originated", "label": "Originated", "field": "date_originated", "align": "left", "sortable": True},
                            {"name": "actions", "label": "", "field": "actions", "align": "right"},
                        ],
                        rows=records,
                        row_key="id",
                        pagination=10,
                    ).props("flat bordered separator=horizontal").classes("erms-page-table")
                    record_table.bind_filter_from(contained_record_filter, "value")
                    add_timestamp_slots(record_table, ["date_originated"])
                    record_table.add_slot("body-cell-actions", '<q-td :props="props"><q-btn flat round :icon="props.row._is_favourite ? \'favorite\' : \'favorite_border\'" :color="props.row._is_favourite ? \'red\' : \'primary\'" :aria-label="props.row._is_favourite ? \'Remove from favourites\' : \'Add to favourites\'" @click.stop="$parent.$emit(\'toggle_favourite\', props.row)"><q-tooltip>{{ props.row._is_favourite ? \'Remove from favourites\' : \'Add to favourites\' }}</q-tooltip></q-btn><q-btn flat round icon="open_in_new" color="primary" @click="$parent.$emit(\'open_record\', props.row)"><q-tooltip>Open record</q-tooltip></q-btn><q-btn flat round icon="history" color="blue-grey" @click="$parent.$emit(\'history\', props.row)"><q-tooltip>Event history</q-tooltip></q-btn></q-td>')
                    record_table.on("open_record", lambda event: show_record_details(event.args))
                    record_table.on("history", lambda event: show_entity_history("records", event.args))
                    async def toggle_contained_record(event) -> None:
                        row = event.args
                        selected = await toggle_favourite("records", row["id"])
                        for table_row in record_table.rows:
                            if table_row["id"] == row["id"]:
                                table_row["_is_favourite"] = selected
                                break
                        record_table.update()
                    record_table.on("toggle_favourite", toggle_contained_record)
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)

    def render_recent_section(spec: EntitySpec) -> None:
        refresh_control: dict[str, Any] = {}

        async def refresh_recent() -> None:
            refresh_control["button"].props("loading disable")
            try:
                await load_recent(spec)
                ui.notify("Recent items refreshed", color="positive")
                render_table(spec)
            except ApiError as error:
                refresh_control["button"].props(remove="loading disable")
                ui.notify(error_message(error), color="negative", close_button=True)

        with ui.row().classes("w-full items-center px-5 pt-5"):
            ui.label("Start where you left off").classes("text-lg font-semibold")
            ui.space()
            refresh_control["button"] = ui.button(
                "Refresh", icon="refresh", on_click=refresh_recent,
            ).props("flat dense no-caps color=primary").tooltip(
                "Reload recently created and updated items"
            )
        with ui.row().classes("w-full px-5 pb-5 gap-6 items-start"):
            for heading, rows, icon, color in (
                ("Recently created", state["recent_created"], "add_circle", "positive"),
                ("Recently updated", state["recent_updated"], "history", "primary"),
            ):
                with ui.column().classes("grow gap-2 min-w-[320px]"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon, color=color)
                        ui.label(heading).classes("font-semibold text-slate-700")
                    if not rows:
                        ui.label("Nothing here yet").classes("text-sm text-slate-400 py-3")
                    for item in rows:
                        click_handler = (
                            (lambda _, entry=item: open_aggregation(entry))
                            if spec.key == "aggregations"
                            else (lambda _, entry=item: show_record_details(entry))
                        )
                        with ui.card().classes("recent-card cursor-pointer w-full px-3 py-2 shadow-none").on("click", click_handler):
                            with ui.row().classes("items-center no-wrap w-full gap-2"):
                                ui.avatar(
                                    icon="folder" if spec.key == "aggregations" else "description",
                                    color="blue-1",
                                    text_color="primary",
                                    size="32px",
                                )
                                with ui.column().classes("gap-0 grow"):
                                    ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                                    number = item.get("aggregation_number") or item.get("record_number")
                                    ui.label(number).classes("text-xs text-slate-400 leading-tight")
                                ui.icon("chevron_right", size="18px").classes("text-slate-300")

    def render_entity_favourites_section(spec: EntitySpec) -> None:
        preview_host = ui.column().classes("w-full gap-2 px-5 pt-5")
        limit = dashboard_favourite_item_limit()
        resource = spec.key
        singular = "aggregation" if resource == "aggregations" else "record"
        heading = f"Favourite {resource}"
        icon = "folder" if resource == "aggregations" else "description"

        async def open_favourite(item: dict[str, Any]) -> None:
            try:
                entity = await api.get(resource, item["id"])
                if resource == "aggregations":
                    await open_aggregation(entity)
                else:
                    await show_record_details(entity)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        def render_entry(item: dict[str, Any], *, after_remove: Any) -> None:
            with ui.row().classes(
                "recent-card cursor-pointer w-full items-center no-wrap px-3 py-2 gap-3"
            ).on("click", lambda _, selected=item: open_favourite(selected)):
                ui.icon(icon, color="primary")
                with ui.column().classes("gap-0 grow min-w-0"):
                    ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                    number = item.get("aggregation_number") or item.get("record_number")
                    ui.label(number or f"{singular.title()} #{item['id']}").classes(
                        "text-xs text-slate-400"
                    )
                    if resource == "records":
                        aggregation = " — ".join(filter(None, (
                            item.get("aggregation_number"), item.get("aggregation_title"),
                        )))
                        if aggregation:
                            ui.label(aggregation).classes("text-xs text-slate-400 line-clamp-1")
                remove_button = ui.button(icon="favorite", color="red").props(
                    "flat round dense aria-label='Remove from favourites'"
                )
                remove_button.tooltip("Remove from favourites")
                remove_button.on(
                    "click", lambda _, selected=item: after_remove(selected),
                    js_handler=STOP_PROPAGATION_CLICK_HANDLER,
                )
                ui.icon("chevron_right").classes("text-slate-300")

        def show_all() -> None:
            dialog = ui.dialog()
            with dialog, ui.card().classes("w-[760px] max-w-full max-h-[85vh]"):
                with ui.row().classes("w-full items-center"):
                    ui.label(heading).classes("text-xl font-semibold")
                    ui.space()
                    ui.button(icon="close", on_click=dialog.close).props("flat round")
                complete_host = ui.column().classes("w-full gap-2 max-h-[65vh] overflow-y-auto")

            def render_complete() -> None:
                complete_host.clear()
                with complete_host:
                    items = state["favourites"][resource]
                    if not items:
                        ui.label(f"No favourite {resource}").classes("text-sm text-slate-400 py-4")
                    for item in items:
                        render_entry(
                            item,
                            after_remove=lambda selected: remove_favourite(
                                selected, refresh_dialog=render_complete,
                            ),
                        )

            render_complete()
            dialog.open()

        async def remove_favourite(
            item: dict[str, Any], *, refresh_dialog: Any | None = None,
        ) -> None:
            selected = await toggle_favourite(resource, item["id"])
            if selected:
                return
            state["favourites"][resource] = [
                row for row in state["favourites"][resource]
                if int(row["id"]) != int(item["id"])
            ]
            render_table(spec)
            if refresh_dialog is not None:
                refresh_dialog()

        def render_preview() -> None:
            preview_host.clear()
            items = state["favourites"][resource]
            with preview_host:
                with ui.row().classes("w-full items-center gap-2"):
                    ui.icon("favorite", color="red")
                    ui.label(heading).classes("text-lg font-semibold")
                    ui.badge(str(len(items)), color="blue-grey").props("outline")
                    ui.space()
                    if len(items) > limit:
                        ui.button(
                            f"View all ({len(items)})", icon="open_in_full",
                            on_click=show_all,
                        ).props("flat dense no-caps color=primary")
                if not items:
                    ui.label(f"No favourite {resource}").classes("text-sm text-slate-400 py-2")
                else:
                    with ui.grid(columns=2).classes("w-full gap-3"):
                        for item in items[:limit]:
                            render_entry(item, after_remove=remove_favourite)

        render_preview()

    async def show_profile_privilege_editor(profile: dict[str, Any]) -> None:
        try:
            all_privileges, selected, impact = await asyncio.gather(
                api.list("privileges"), api.profile_privileges(profile["id"]),
                api.profile_impact(profile["id"]),
            )
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        selected_ids = {item["id"] for item in selected}
        dialog = ui.dialog()
        controls: dict[int, Any] = {}
        privilege_entries: list[tuple[dict[str, Any], Any]] = []
        category_sections: dict[str, tuple[Any, list[tuple[dict[str, Any], Any]]]] = {}
        with dialog, ui.card().classes("w-[760px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)]"):
            ui.label(f"Privileges — {profile['name']}").classes("text-xl font-semibold")
            ui.label(
                f"Changes affect {impact['role_count']} role(s) and {impact['user_count']} assigned user(s)."
            ).classes("text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2")
            privilege_search = ui.input(
                "Find privileges",
                placeholder="Search by code, name, or description",
            ).props("outlined dense clearable debounce=200").classes("w-full")
            with ui.column().classes("w-full gap-2 overflow-y-auto max-h-[55vh]"):
                current_category = None
                for privilege in all_privileges:
                    if privilege["category"] != current_category:
                        current_category = privilege["category"]
                        category_label = ui.label(
                            current_category.replace("_", " ").upper()
                        ).classes(
                            "text-xs tracking-wider text-slate-500 font-semibold mt-2"
                        )
                        category_sections[current_category] = (category_label, [])
                    with ui.row().classes("w-full items-start") as privilege_entry:
                        with ui.column().classes("w-full gap-0"):
                            controls[privilege["id"]] = ui.checkbox(
                                f"{privilege['name']} ({privilege['code']})",
                                value=privilege["id"] in selected_ids,
                            )
                            ui.label(
                                privilege_help_text(
                                    privilege["code"], privilege.get("description")
                                )
                            ).classes(
                                "text-xs leading-5 text-slate-500 pl-10 -mt-1 pr-2"
                            )
                    entry = (privilege, privilege_entry)
                    privilege_entries.append(entry)
                    category_sections[current_category][1].append(entry)

            def filter_privileges() -> None:
                query = privilege_search.value or ""
                for privilege, entry_element in privilege_entries:
                    entry_element.set_visibility(privilege_matches_search(privilege, query))
                for _, (category_label, entries) in category_sections.items():
                    category_label.set_visibility(
                        any(privilege_matches_search(privilege, query) for privilege, _ in entries)
                    )

            privilege_search.on_value_change(lambda _: filter_privileges())
            with ui.row().classes(
                "w-full items-start gap-2 rounded-lg border border-amber-200 "
                "bg-amber-50 px-3 py-2"
            ) as unrestricted_profile_warning:
                ui.icon("warning_amber", color="amber-9", size="20px").classes(
                    "mt-0.5 shrink-0"
                )
                ui.label(
                    "This profile contains every defined privilege. Assigning it to a role "
                    "gives that role unrestricted system capabilities, subject to security "
                    "clearance and resource ACL checks. Use purpose-specific profiles before "
                    "production. This warning does not prevent saving."
                ).classes("text-xs leading-5 text-amber-10")

            def update_unrestricted_profile_warning() -> None:
                unrestricted_profile_warning.set_visibility(
                    bool(controls) and all(control.value for control in controls.values())
                )

            for privilege_control in controls.values():
                privilege_control.on_value_change(
                    lambda _: update_unrestricted_profile_warning()
                )
            update_unrestricted_profile_warning()
            reason = ui.textarea("Reason for changing this profile", placeholder="Required").props(
                "outlined autogrow"
            ).classes("w-full")

            async def save_privileges() -> None:
                change_reason = (reason.value or "").strip()
                if not change_reason:
                    ui.notify("A reason is required", color="warning")
                    return
                try:
                    await api.replace_profile_privileges(
                        profile["id"], profile["version"],
                        [identifier for identifier, control in controls.items() if control.value],
                        reason=change_reason,
                    )
                    dialog.close()
                    ui.notify("Profile privileges saved", color="positive")
                    await select_entity("profiles")
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                ui.button("Save privileges", icon="save", on_click=save_privileges).props("unelevated no-caps")
        dialog.open()

    def render_table(spec: EntitySpec) -> None:
        table_container.clear()
        with table_container:
            if spec.key in {"aggregations", "records"}:
                render_entity_favourites_section(spec)
            if spec.search_first and not state["searched"]:
                if spec.key == "classifications":
                    with ui.column().classes("w-full items-center py-12 gap-2 text-slate-500"):
                        ui.icon("manage_search", size="42px").classes("text-primary")
                        ui.label(
                            "Search classifications by code, title, description, or keywords."
                        ).classes("font-medium")
                        ui.label("Partial matching is automatic; wildcard characters are not required.").classes("text-xs")
                    return
                render_recent_section(spec)
                return
            if spec.key == "aggregations":
                ui.separator().classes("erms-results-divider")
                with ui.row().classes("w-full items-center px-5 pt-2 gap-2"):
                    ui.icon("search", color="primary")
                    ui.label("Search results").classes("text-lg font-semibold")
                    ui.badge(str(len(state["rows"])), color="blue-grey").props("outline")
            lifecycle_filter = None
            account_type_filter = None
            administration_filter = None
            visible_rows = state["rows"]
            result_filter = None
            if spec.key in {"aggregations", "records"}:
                with ui.row().classes("w-full items-center px-5 pt-2 gap-3"):
                    result_filter = ui.input(
                        "Filter displayed results",
                        placeholder="Type to filter across the table",
                    ).props("outlined dense clearable debounce=250").classes("w-96 max-w-full")
                    ui.space()
                    ui.label(f"{len(visible_rows)} results").classes("text-sm text-slate-500")
            if spec.key in {"org-units", "roles", "users"}:
                status_options = {
                    "all": "All statuses",
                    "active": "Active",
                    "inactive": "Inactive",
                }
                if spec.key == "users":
                    status_options["suspended"] = "Suspended"
                filter_labels = {
                    "org-units": "Search code, name, or parent unit",
                    "roles": "Search code, name, or organization unit",
                    "users": "Search name or email",
                }
                selected_lifecycle_filter = state.get("lifecycle_filter", "all")
                if selected_lifecycle_filter not in status_options:
                    selected_lifecycle_filter = "all"
                    state["lifecycle_filter"] = "all"
                with ui.row().classes(
                    "w-full items-center gap-3 px-5 pt-2 pb-1 mb-2"
                ):
                    administration_filter = ui.input(
                        filter_labels[spec.key],
                        placeholder="Type to filter this table",
                    ).props("outlined dense clearable debounce=250").classes("w-96 max-w-full")
                    ui.space()
                    if spec.key == "users":
                        account_type_filter = ui.select(
                            {"all": "All account types", "person": "Person", "service": "Service"},
                            value=state.get("account_type_filter", "all"),
                            label="Account type",
                        ).props("outlined dense options-dense").classes("w-48")
                    lifecycle_filter = ui.select(
                        status_options,
                        value=selected_lifecycle_filter,
                        label="Status",
                    ).props("outlined dense options-dense").classes("w-48")
            sortable_relationships = {"parent_org_unit_display", "org_unit_display", "profile_display"}
            for row in visible_rows:
                for relationship_key in sortable_relationships:
                    relationship = row.get(relationship_key) or {}
                    row[f"_{relationship_key}_sort"] = " ".join(
                        str(relationship.get(part) or "") for part in ("name", "code")
                    ).strip().casefold()
            columns = [
                {
                    "name": key,
                    "label": label,
                    "field": f"_{key}_sort" if key in sortable_relationships else key,
                    "align": "left",
                    "sortable": (
                        key != "_avatar"
                        and (not key.endswith("_display") or key in sortable_relationships)
                    ),
                }
                for key, label in spec.columns
            ]
            columns.append({"name": "actions", "label": "", "field": "actions", "align": "right"})
            if spec.key == "profiles":
                profile_widths = {
                    "code": "width: 150px",
                    "name": "width: 230px",
                    "description": "width: auto",
                    "is_system": "width: 110px",
                    "actions": "width: 150px",
                }
                for column in columns:
                    column["style"] = profile_widths.get(column["name"], "")
                    column["headerStyle"] = profile_widths.get(column["name"], "")
            if spec.key in {"aggregations", "records"}:
                for row in visible_rows:
                    row["_is_favourite"] = favourite_state(spec.key, row["id"])
            table = ui.table(
                columns=columns,
                rows=visible_rows,
                row_key="id",
                pagination={"rowsPerPage": 25},
            ).props(
                'flat bordered separator=horizontal :rows-per-page-options="[10,25,50,100]"'
            ).classes(
                "erms-page-table erms-profiles-table"
                if spec.key == "profiles" else "erms-page-table"
            )
            if result_filter is not None:
                table.bind_filter_from(result_filter, "value")
            if administration_filter is not None:
                def searchable_text(value: Any) -> str:
                    if isinstance(value, dict):
                        return " ".join(searchable_text(item) for item in value.values())
                    if isinstance(value, (list, tuple)):
                        return " ".join(searchable_text(item) for item in value)
                    return "" if value is None else str(value)

                def apply_administration_filters() -> None:
                    state["lifecycle_filter"] = lifecycle_filter.value
                    if account_type_filter is not None:
                        state["account_type_filter"] = account_type_filter.value
                    query = (administration_filter.value or "").strip().casefold()
                    selected_status = lifecycle_filter.value
                    selected_account_type = (
                        account_type_filter.value if account_type_filter is not None else "all"
                    )
                    table.rows = [
                        row for row in state["rows"]
                        if (
                            selected_status == "all"
                            or row.get("effective_status", row.get("status")) == selected_status
                        )
                        and (
                            selected_account_type == "all"
                            or row.get("account_type") == selected_account_type
                        )
                        and (
                            not query
                            or query in " ".join(
                                searchable_text(row.get(key)).casefold()
                                for key, _ in spec.columns
                                if key != "_avatar"
                            )
                        )
                    ]
                    table.update()

                administration_filter.on_value_change(apply_administration_filters)
                lifecycle_filter.on_value_change(apply_administration_filters)
                if account_type_filter is not None:
                    account_type_filter.on_value_change(apply_administration_filters)
                apply_administration_filters()
            add_timestamp_slots(
                table, [key for key, _ in spec.columns if key.startswith("date_")]
            )
            if spec.key == "users":
                table.add_slot("body-cell-_avatar", '''
                    <q-td :props="props" style="width: 56px">
                      <q-avatar size="38px" :style="{ backgroundColor: props.row._avatar.color, color: 'white' }">
                        {{ props.row._avatar.initials }}
                      </q-avatar>
                    </q-td>
                ''')
                table.add_slot("body-cell-account_type", '''
                    <q-td :props="props">
                      <span>{{ props.value === 'person' ? 'Person' : 'Service' }}</span>
                    </q-td>
                ''')
            if spec.key == "profiles":
                table.add_slot("body-cell-name", '''
                    <q-td :props="props">
                      <div class="ellipsis">{{ props.value }}</div>
                      <q-tooltip>{{ props.value }}</q-tooltip>
                    </q-td>
                ''')
                table.add_slot("body-cell-description", '''
                    <q-td :props="props" class="profile-description-cell">
                      {{ props.value || '—' }}
                      <q-tooltip>{{ props.value || 'No description' }}</q-tooltip>
                    </q-td>
                ''')
                table.add_slot("body-cell-is_system", '''
                    <q-td :props="props">
                      <q-badge
                        :color="props.value ? 'blue-grey-7' : 'grey-5'"
                        :label="props.value ? 'Built-in' : 'Custom'"
                        outline
                      >
                        <q-tooltip>
                          {{ props.value
                            ? 'Supplied by Wathiq. It cannot be deleted and its code cannot be renamed.'
                            : 'Created by your organization.' }}
                        </q-tooltip>
                      </q-badge>
                    </q-td>
                ''')
            for key, _ in spec.columns:
                if not key.endswith("_display"):
                    continue
                if key == "type_display":
                    table.add_slot("body-cell-type_display", """
                        <q-td :props="props">
                          <div class="row items-center no-wrap q-gutter-sm">
                            <q-avatar size="30px" color="blue-1" text-color="primary" :icon="props.row.is_terminal ? 'label' : 'schema'" />
                            <span class="text-weight-medium">{{ props.row.is_terminal ? 'Terminal' : 'Branch' }}</span>
                          </div>
                        </q-td>
                    """)
                    continue
                relationship_icon = {
                    "parent_org_unit_display": "corporate_fare",
                    "org_unit_display": "corporate_fare",
                    "aggregation_display": "folder",
                    "scheme_display": "account_tree",
                    "profile_display": "admin_panel_settings",
                }.get(key, "link")
                relationship_template = """
                    <q-td :props="props">
                      <div v-if="props.row.__FIELD__" class="row items-center no-wrap q-gutter-sm">
                        <q-avatar size="30px" color="blue-1" text-color="primary" icon="__ICON__" />
                        <div class="column">
                          <span class="text-weight-medium relationship-cell-name">{{ props.row.__FIELD__.name }}</span>
                          <q-badge v-if="props.row.__FIELD__.code" outline color="primary" :label="props.row.__FIELD__.code" class="self-start" />
                        </div>
                      </div>
                      <span v-else class="text-grey-5">—</span>
                    </q-td>
                """.replace("__ICON__", relationship_icon).replace("__FIELD__", key)
                if key == "profile_display":
                    relationship_template = relationship_template.replace(
                        '<q-badge v-if="props.row.__FIELD__.code" outline color="primary" :label="props.row.__FIELD__.code" class="self-start" />'.replace("__FIELD__", key),
                        '<q-badge v-if="props.row.profile_display.code" outline :color="props.row.profile_display.code === \'ALL_PRIVS\' ? \'warning\' : \'primary\'" :label="props.row.profile_display.code === \'ALL_PRIVS\' ? \'Compatibility profile\' : props.row.profile_display.code" class="self-start"><q-tooltip v-if="props.row.profile_display.code === \'ALL_PRIVS\'">Review and replace with a purpose-specific profile</q-tooltip></q-badge>',
                    )
                table.add_slot(f"body-cell-{key}", relationship_template)
            if any(key == "effective_status" for key, _ in spec.columns):
                table.add_slot("body-cell-effective_status", '''
                    <q-td :props="props">
                      <q-badge
                        :color="props.value === 'active' ? 'positive' : (props.value === 'suspended' ? 'warning' : 'grey-7')"
                        :label="props.value"
                      ><q-tooltip>{{ props.row._inactive_reason }}</q-tooltip></q-badge>
                    </q-td>
                ''')
            if any(key == "status" for key, _ in spec.columns):
                table.add_slot("body-cell-status", '''
                    <q-td :props="props">
                      <q-badge
                        :color="props.value === 'active' ? 'positive' : (props.value === 'suspended' ? 'warning' : 'grey-7')"
                        :label="props.value"
                      />
                    </q-td>
                ''')
            if spec.key in {"records", "aggregations"}:
                closed_label = f"Closed {spec.singular} metadata cannot be changed"
                buttons = '<q-btn flat round dense :icon="props.row._is_favourite ? \'favorite\' : \'favorite_border\'" :color="props.row._is_favourite ? \'red\' : \'primary\'" :aria-label="props.row._is_favourite ? \'Remove from favourites\' : \'Add to favourites\'" @click.stop="$parent.$emit(\'toggle_favourite\', props.row)"><q-tooltip>{{ props.row._is_favourite ? \'Remove from favourites\' : \'Add to favourites\' }}</q-tooltip></q-btn>'
                buttons += f'<q-btn flat round dense icon="edit" color="primary" :disable="props.row._effectively_closed" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>{{{{ props.row._effectively_closed ? \'{closed_label}\' : \'Edit\' }}}}</q-tooltip></q-btn>'
            elif spec.key in {"privileges", "permissions"}:
                buttons = ''
            else:
                buttons = '<q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'
            if spec.key == "org-units":
                buttons = '<q-btn flat round dense icon="open_in_new" color="primary" @click="$parent.$emit(\'open_org_unit\', props.row)"><q-tooltip>Open organization unit</q-tooltip></q-btn>' + buttons
            if spec.key == "roles":
                buttons = '<q-btn flat round dense icon="open_in_new" color="primary" @click="$parent.$emit(\'open_role\', props.row)"><q-tooltip>Open role</q-tooltip></q-btn>' + buttons
            if spec.key not in {"privileges", "permissions"}:
                buttons += '<q-btn flat round dense icon="history" color="blue-grey" @click="$parent.$emit(\'history\', props.row)"><q-tooltip>Event history</q-tooltip></q-btn>'
            if spec.key == "records":
                buttons += '<q-btn flat round dense icon="attach_file" color="secondary" @click="$parent.$emit(\'components\', props.row)"><q-tooltip>Digital components</q-tooltip></q-btn>'
            if spec.key == "aggregations":
                buttons = '<q-btn flat round dense icon="folder_open" color="secondary" @click="$parent.$emit(\'open_aggregation\', props.row)"><q-tooltip>Open aggregation</q-tooltip></q-btn>' + buttons
                buttons += '<q-btn v-if="props.row._directly_closed" flat round dense icon="lock_open" color="primary" @click="$parent.$emit(\'reopen\', props.row)"><q-tooltip>Reopen aggregation</q-tooltip></q-btn>'
            if spec.key in {"users", "roles"}:
                buttons += '<q-btn flat round dense icon="group" color="secondary" @click="$parent.$emit(\'memberships\', props.row)"><q-tooltip>Role assignments</q-tooltip></q-btn>'
            if spec.key == "profiles":
                buttons += '<q-btn flat round dense icon="key" color="secondary" @click="$parent.$emit(\'profile_privileges\', props.row)"><q-tooltip>Manage privileges</q-tooltip></q-btn>'
            if spec.key == "users":
                buttons = '<q-btn flat round dense icon="open_in_new" color="primary" @click="$parent.$emit(\'open_user\', props.row)"><q-tooltip>Open user</q-tooltip></q-btn>' + buttons
                buttons += '<q-btn flat round dense icon="password" color="orange" @click="$parent.$emit(\'temporary_password\', props.row)"><q-tooltip>Issue temporary password</q-tooltip></q-btn>'
            if spec.key in {"org-units", "roles", "users"}:
                buttons += LIFECYCLE_ACTION_BUTTONS
            if spec.key == "users":
                buttons += USER_SUSPENSION_ACTION_BUTTONS
            if spec.key == "classification-schemes":
                buttons += '<q-btn v-if="!props.row.date_published" flat round dense icon="publish" color="primary" @click="$parent.$emit(\'publish_scheme\', props.row)"><q-tooltip>Publish now</q-tooltip></q-btn>'
                buttons += '<q-btn flat round dense :icon="props.row.date_deactivated ? \'toggle_on\' : \'toggle_off\'" :color="props.row.date_deactivated ? \'positive\' : \'negative\'" @click="$parent.$emit(\'scheme_lifecycle\', props.row)"><q-tooltip>{{ props.row.date_deactivated ? \'Reactivate\' : \'Deactivate\' }}</q-tooltip></q-btn>'
            table.add_slot("body-cell-actions", f'<q-td :props="props">{buttons}</q-td>')
            table.on("edit", lambda event: open_editor(event.args))
            table.on("history", lambda event, resource=spec.key: show_entity_history(resource, event.args))
            if spec.key == "profiles":
                table.on("profile_privileges", lambda event: show_profile_privilege_editor(event.args))
            if spec.key == "org-units":
                table.on("open_org_unit", lambda event: select_organization_unit_details(event.args["id"]))
            if spec.key == "roles":
                table.on("open_role", lambda event: select_role_details(event.args["id"]))
            if spec.key in {"aggregations", "records"}:
                async def toggle_table_favourite(event) -> None:
                    row = event.args
                    selected = await toggle_favourite(spec.key, row["id"])
                    for table_row in table.rows:
                        if table_row["id"] == row["id"]:
                            table_row["_is_favourite"] = selected
                            break
                    table.update()
                    if spec.key in {"aggregations", "records"}:
                        await reload_favourites()
                        render_table(spec)
                table.on("toggle_favourite", toggle_table_favourite)
            if spec.key == "records":
                table.on("components", lambda event: show_components(event.args))
            if spec.key == "aggregations":
                table.on("open_aggregation", lambda event: open_aggregation(event.args))
                async def reopen_from_table(event) -> None:
                    row = event.args
                    try:
                        await api.update(
                            "aggregations", row["id"], row["version"], {"date_closed": None}
                        )
                        ui.notify("Aggregation reopened", color="positive")
                        await load_recent(spec)
                        if state["searched"]:
                            await load_rows(repeat_search=True)
                        else:
                            render_table(spec)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                table.on("reopen", reopen_from_table)
            if spec.key == "classification-schemes":
                async def publish_scheme(event) -> None:
                    row = event.args
                    try:
                        await api.request(
                            "POST", f"/api/v1/classification-schemes/{row['id']}/publish",
                            headers={"If-Match": str(row["version"])},
                        )
                        ui.notify("Classification scheme published", color="positive")
                        await load_rows(repeat_search=True)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                async def change_scheme_lifecycle(event) -> None:
                    row = event.args
                    action = "reactivate" if row.get("date_deactivated") else "deactivate"
                    try:
                        await api.request(
                            "POST", f"/api/v1/classification-schemes/{row['id']}/{action}",
                            headers={
                                "If-Match": str(row["version"]),
                                "X-Change-Reason": f"{action.title()} from classification administration",
                            },
                        )
                        ui.notify(f"Classification scheme {action}d", color="positive")
                        await load_rows(repeat_search=True)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                table.on("publish_scheme", publish_scheme)
                table.on("scheme_lifecycle", change_scheme_lifecycle)
            if spec.key in {"users", "roles"}:
                table.on(
                    "memberships",
                    lambda event, user_view=spec.key == "users": show_memberships(
                        event.args, for_user=user_view
                    ),
                )
            if spec.key == "users":
                table.on("open_user", lambda event: select_user_details(event.args["id"]))
                async def issue_password(event) -> None:
                    try:
                        result = await api.issue_temporary_password(event.args["id"])
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                        return
                    dialog = ui.dialog().props("persistent")
                    with dialog, ui.card().classes("w-[520px] max-w-full"):
                        ui.label("Temporary password").classes("text-xl font-semibold")
                        ui.label("Copy this password now. It will not be shown again.").classes("text-sm text-slate-500")
                        ui.code(result["temporary_password"]).classes("w-full text-lg")
                        ui.label(f"Expires {format_timestamp(result['expires_at'])}").classes("text-xs text-slate-400")
                        with ui.row().classes("w-full justify-end"):
                            ui.button("I have copied it", on_click=dialog.close).props("unelevated no-caps")
                    dialog.open()
                table.on("temporary_password", issue_password)
                async def change_suspension(event, *, suspended: bool) -> None:
                    row = event.args
                    action = "Suspend" if suspended else "Unsuspend"
                    dialog = ui.dialog()
                    with dialog, ui.card().classes("w-[520px] max-w-full"):
                        ui.label(f"{action} user?").classes("text-xl font-semibold")
                        ui.label(row.get("name") or f"#{row['id']}").classes("font-medium")
                        ui.label(
                            "All active sessions will be revoked. The user must sign in again after being unsuspended."
                            if suspended else
                            "The account will become active again. Previously revoked sessions will not be restored."
                        ).classes("text-sm text-slate-600")

                        async def proceed() -> None:
                            try:
                                saved = await api.set_user_suspended(
                                    row["id"], row["version"], suspended=suspended,
                                )
                                dialog.close()
                                if suspended and row["id"] == auth_state["principal"]["user"]["id"]:
                                    app.storage.user.pop("session_token", None)
                                    api.set_session_token(None)
                                    clear_signed_in_identity()
                                    login_dialog.open()
                                    return
                                state["rows"] = [
                                    saved if item["id"] == saved["id"] else item
                                    for item in state["rows"]
                                ]
                                state["rows"] = await decorate_for_spec(spec, state["rows"])
                                render_table(spec)
                                ui.notify(f"User {action.lower()}ed", color="positive")
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                            ui.button(action, on_click=proceed).props("unelevated no-caps")
                    dialog.open()

                table.on("suspend_user", lambda event: change_suspension(event, suspended=True))
                table.on("unsuspend_user", lambda event: change_suspension(event, suspended=False))
            if spec.key in {"org-units", "roles", "users"}:
                async def confirm_lifecycle(event) -> None:
                    row = event.args
                    activating = row.get("status") == "inactive"
                    action = "Activate" if activating else "Deactivate"
                    dialog = ui.dialog()
                    with dialog, ui.card().classes("w-[520px] max-w-full"):
                        ui.label(f"{action} {spec.singular}?").classes("text-xl font-semibold")
                        ui.label(row.get("name") or row.get("code") or f"#{row['id']}").classes("font-medium")
                        if spec.key == "org-units":
                            message = (
                                "Its roles and descendant-unit roles become effective again unless independently inactive."
                                if activating else
                                "Roles in this unit and every descendant unit will become ineffective; users and assignments remain unchanged."
                            )
                        elif spec.key == "roles":
                            message = (
                                "Existing assignments can contribute authorization again when otherwise valid."
                                if activating else
                                "Existing users and assignments remain unchanged, but this role contributes no authorization."
                            )
                        else:
                            message = (
                                "The user can authenticate again; existing role assignments are retained."
                                if activating else
                                "All active login sessions will be revoked. Role assignments are retained but ineffective."
                            )
                        ui.label(message).classes("text-sm text-slate-600")

                        async def proceed() -> None:
                            try:
                                saved = await api.set_active(
                                    spec.key, row["id"], row["version"], active=activating,
                                )
                                dialog.close()
                                if (
                                    spec.key == "users" and not activating
                                    and row["id"] == auth_state["principal"]["user"]["id"]
                                ):
                                    app.storage.user.pop("session_token", None)
                                    api.set_session_token(None)
                                    clear_signed_in_identity()
                                    login_dialog.open()
                                    return
                                state["rows"] = [
                                    saved if item["id"] == saved["id"] else item
                                    for item in state["rows"]
                                ]
                                state["rows"] = await decorate_for_spec(spec, state["rows"])
                                render_table(spec)
                                ui.notify(f"{spec.singular.capitalize()} {action.lower()}d", color="positive")
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative", close_button=True)

                        with ui.row().classes("w-full justify-end gap-2"):
                            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                            ui.button(action, on_click=proceed, icon="toggle_on" if activating else "toggle_off").props(
                                f"unelevated no-caps color={'positive' if activating else 'negative'}"
                            )
                    dialog.open()
                table.on("lifecycle", confirm_lifecycle)

    def populate_user_menu(principal: dict[str, Any]) -> None:
        drawer.show()
        header_network.set_visibility(True)
        auth_state["principal"] = principal
        privileges = set(principal.get("global_privileges", []))
        refresh_drawer_visibility(privileges)
        user = principal["user"]
        current_user_name.text = user["name"]
        current_user_email.text = user.get("email") or user["account_type"].title()
        avatar = user_avatar(user)
        current_user_avatar_initials.text = avatar["initials"]
        current_user_avatar.style(
            replace=f"background:{avatar['color']} !important;color:white !important"
        )
        previous_login_at = principal.get("previous_login_at")
        current_user_last_login.text = (
            format_timestamp(previous_login_at) if previous_login_at else "First sign-in"
        )
        current_user_roles.clear()
        with current_user_roles:
            if not principal["roles"]:
                ui.label("No assigned roles").classes("text-xs text-slate-400")
            for role in principal["roles"]:
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    ui.icon("badge", size="18px").classes("text-primary")
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(role["name"]).classes("text-sm font-medium line-clamp-1")
                        ui.label(role["org_unit"]["name"]).classes("text-xs text-slate-400 line-clamp-1")

    async def show_change_password() -> None:
        forced_change = bool(
            (auth_state.get("principal") or {}).get("must_change_password")
        )
        dialog = ui.dialog().props("persistent")
        with dialog, ui.card().classes("w-[480px] max-w-full"):
            ui.label(
                "Set a new password" if forced_change else "Change password"
            ).classes("text-xl font-semibold")
            if forced_change:
                ui.label(
                    "Your temporary password must be replaced before you can continue."
                ).classes("text-sm text-slate-500")
            current = ui.input(
                "Temporary password" if forced_change else "Current password",
                password=True,
                password_toggle_button=True,
            ).props("outlined autocomplete=current-password").classes("w-full")
            new = ui.input("New password", password=True, password_toggle_button=True).props("outlined").classes("w-full")
            confirm = ui.input("Confirm new password", password=True).props("outlined").classes("w-full")

            async def save_password() -> None:
                if new.value != confirm.value:
                    ui.notify("New passwords do not match", color="warning")
                    return
                try:
                    await api.change_password(current.value or "", new.value or "")
                    dialog.close()
                    ui.notify("Password changed", color="positive")
                    populate_user_menu(await api.me())
                    await select_dashboard()
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            async def return_to_sign_in() -> None:
                # A forced-change session is deliberately restricted. Let the
                # person abandon it safely when the temporary password is no
                # longer available, instead of trapping them in this dialog.
                dialog.close()
                await sign_out()

            with ui.row().classes("w-full justify-end"):
                if forced_change:
                    ui.button(
                        "Back to sign in", icon="arrow_back",
                        on_click=return_to_sign_in,
                    ).props("flat no-caps")
                else:
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Set new password" if forced_change else "Change password",
                    icon="password",
                    on_click=save_password,
                ).props("unelevated")
        dialog.open()

    async def sign_out() -> None:
        # Close the overlay immediately; waiting for the API logout first leaves
        # the menu above the persistent login dialog during slower requests.
        user_menu.close()
        try:
            await api.logout()
        except ApiError:
            pass
        app.storage.user.pop("session_token", None)
        app.storage.user.pop("organization_browser_state", None)
        api.set_session_token(None)
        clear_signed_in_identity()
        login_dialog.open()

    async def select_login_sessions(user_id: int | None = None) -> None:
        if user_id is None:
            register_navigation("login-sessions", "Login sessions")
        show_authenticated_view()
        state.update(resource="login-sessions", rows=[], searched=True, aggregation_detail=None)
        title.text = "Login sessions"
        subtitle.text = (
            "Review and revoke sessions for the selected user"
            if user_id is not None else "Review and revoke authenticated sessions"
        )
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        with table_container:
            outer = ui.column().classes("w-full p-5 gap-4")

        async def load_sessions() -> None:
            try:
                rows = await api.login_sessions(user_id=user_id)
            except ApiError as error:
                ui.notify(error_message(error), color="negative")
                return
            is_admin = "identity.sessions.administer" in set(
                auth_state["principal"].get("global_privileges", [])
            )
            for row in rows:
                row["can_revoke_all"] = is_admin
                row["_user_avatar"] = user_avatar({
                    "id": row.get("user_id"),
                    "name": row.get("user_name"),
                    "email": row.get("user_email"),
                })
            outer.clear()
            with outer:
                with ui.card().classes("w-full shadow-none border border-slate-200 p-4 gap-3"):
                    ui.label("Filter sessions").classes("font-semibold")
                    with ui.grid(columns=4).classes("w-full gap-3"):
                        session_filter = ui.input(
                            "User or client",
                            placeholder="Name, email, IP address or browser",
                        ).props("outlined dense clearable").classes("w-full col-span-2")
                        status_filter = ui.select(
                            {"active": "Active", "expired": "Expired", "revoked": "Revoked"},
                            label="Status", clearable=True,
                        ).props("outlined dense options-dense").classes("w-full")
                        timestamp_field = ui.select(
                            {"date_created": "Signed in", "last_seen_at": "Last activity"},
                            label="Date field", value="date_created",
                        ).props("outlined dense options-dense").classes("w-full")
                        from_filter = ui.input("From").props(
                            "outlined dense clearable type=datetime-local"
                        ).classes("w-full col-span-2")
                        until_filter = ui.input("To").props(
                            "outlined dense clearable type=datetime-local"
                        ).classes("w-full col-span-2")
                    filter_actions = ui.row().classes("w-full justify-end gap-2")
                with ui.row().classes("w-full items-center"):
                    result_summary = ui.label(
                        f"Showing {len(rows)} sessions · "
                        f"{sum(row.get('status') == 'active' for row in rows)} active"
                    ).classes("text-sm text-slate-500")
                    ui.space()
                    ui.button("Refresh", icon="refresh", on_click=load_sessions).props("flat no-caps")
                table = ui.table(
                    columns=[
                        {"name": "user_name", "label": "User", "field": "user_name", "align": "left", "sortable": True},
                        {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
                        {"name": "date_created", "label": "Signed in", "field": "date_created", "align": "left", "sortable": True},
                        {"name": "last_seen_at", "label": "Last activity", "field": "last_seen_at", "align": "left", "sortable": True},
                        {"name": "expires_at", "label": "Expires", "field": "expires_at", "align": "left", "sortable": True},
                        {"name": "client_ip", "label": "IP address", "field": "client_ip", "align": "left", "sortable": True},
                        {"name": "user_agent", "label": "Client", "field": "user_agent", "align": "left", "sortable": True},
                        {"name": "actions", "label": "", "field": "actions", "align": "right"},
                    ], rows=rows, row_key="id", pagination=25,
                ).props("flat bordered wrap-cells").classes("w-full governance-table login-sessions-table")
                add_timestamp_slots(table, ["date_created", "last_seen_at", "expires_at"])
                table.add_slot("body-cell-user_name", '''
                    <q-td :props="props">
                      <div class="row items-center no-wrap q-gutter-sm">
                        <q-avatar size="36px" :style="{ backgroundColor: props.row._user_avatar.color, color: 'white' }">
                          {{ props.row._user_avatar.initials }}
                        </q-avatar>
                        <div class="column">
                          <span class="text-weight-medium">{{ props.row.user_name }}</span>
                          <span class="text-caption text-grey-6">{{ props.row.user_email || 'No email address' }}</span>
                          <q-badge v-if="props.row.is_current" outline color="primary" label="Current session" class="self-start q-mt-xs" />
                        </div>
                      </div>
                    </q-td>
                ''')
                table.add_slot("body-cell-status", '''
                    <q-td :props="props"><q-badge :color="props.value === 'active' ? 'positive' : (props.value === 'revoked' ? 'negative' : 'grey')" :label="props.value" /></q-td>
                ''')
                table.add_slot("body-cell-actions", '''
                    <q-td :props="props">
                      <q-btn-dropdown
                        v-if="props.row.status === 'active'"
                        outline dense no-caps color="negative" icon="logout"
                        label="Force sign-out"
                      >
                        <q-list style="min-width: 245px">
                          <q-item clickable v-close-popup @click="$parent.$emit('revoke', props.row)">
                            <q-item-section avatar><q-icon name="logout" color="negative" /></q-item-section>
                            <q-item-section>
                              <q-item-label>This session</q-item-label>
                              <q-item-label caption>End only this login session</q-item-label>
                            </q-item-section>
                          </q-item>
                          <q-separator v-if="props.row.can_revoke_all" />
                          <q-item v-if="props.row.can_revoke_all" clickable v-close-popup @click="$parent.$emit('revoke_all', props.row)">
                            <q-item-section avatar><q-icon name="devices_off" color="negative" /></q-item-section>
                            <q-item-section>
                              <q-item-label>All sessions for this user</q-item-label>
                              <q-item-label caption>End every active login for this account</q-item-label>
                            </q-item-section>
                          </q-item>
                        </q-list>
                      </q-btn-dropdown>
                    </q-td>
                ''')

                def parsed_timestamp(value: Any) -> datetime | None:
                    if not value:
                        return None
                    try:
                        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                        return parsed.astimezone()
                    except (TypeError, ValueError):
                        return None

                def apply_session_filters() -> None:
                    query = (session_filter.value or "").strip().casefold()
                    status_value = status_filter.value
                    selected_timestamp = timestamp_field.value or "date_created"
                    range_start = parsed_timestamp(from_filter.value)
                    range_end = parsed_timestamp(until_filter.value)
                    filtered_rows = []
                    for row in rows:
                        searchable = " ".join(str(row.get(field) or "") for field in (
                            "user_name", "user_email", "status", "client_ip", "user_agent",
                        )).casefold()
                        occurred = parsed_timestamp(row.get(selected_timestamp))
                        if query and query not in searchable:
                            continue
                        if status_value and row.get("status") != status_value:
                            continue
                        if range_start and (occurred is None or occurred < range_start):
                            continue
                        if range_end and (occurred is None or occurred > range_end):
                            continue
                        filtered_rows.append(row)
                    table.rows = filtered_rows
                    table.update()
                    result_summary.text = (
                        f"Showing {len(filtered_rows)} of {len(rows)} sessions · "
                        f"{sum(row['status'] == 'active' for row in filtered_rows)} active"
                    )
                    result_summary.update()

                def clear_session_filters() -> None:
                    session_filter.value = ""
                    status_filter.value = None
                    timestamp_field.value = "date_created"
                    from_filter.value = ""
                    until_filter.value = ""
                    for control in (
                        session_filter, status_filter, timestamp_field,
                        from_filter, until_filter,
                    ):
                        control.update()
                    apply_session_filters()

                with filter_actions:
                    ui.button("Clear", icon="filter_alt_off", on_click=clear_session_filters).props(
                        "flat dense no-caps"
                    )
                    ui.button("Apply filters", icon="filter_alt", on_click=apply_session_filters).props(
                        "unelevated dense no-caps"
                    )
                session_filter.on("keydown.enter", apply_session_filters)

                async def confirm_revoke(row: dict[str, Any], *, all_for_user: bool = False) -> None:
                    confirmation = ui.dialog()
                    with confirmation, ui.card().classes("w-[460px] max-w-full"):
                        ui.label("Force sign-out?").classes("text-xl font-semibold")
                        scope = "all active sessions for" if all_for_user else "this session for"
                        ui.label(f"This will immediately revoke {scope} {row['user_name']}.").classes("text-sm text-slate-600")

                        async def proceed() -> None:
                            confirmation.close()
                            try:
                                if all_for_user:
                                    await api.revoke_user_sessions(row["user_id"])
                                else:
                                    await api.revoke_session(row["id"])
                                if row.get("is_current"):
                                    app.storage.user.pop("session_token", None)
                                    api.set_session_token(None)
                                    clear_signed_in_identity()
                                    login_dialog.open()
                                else:
                                    ui.notify("Session revoked", color="positive")
                                    await load_sessions()
                            except ApiError as error:
                                ui.notify(error_message(error), color="negative")

                        with ui.row().classes("w-full justify-end"):
                            ui.button("Cancel", on_click=confirmation.close).props("flat")
                            ui.button("Force sign-out", icon="logout", color="negative", on_click=proceed).props("unelevated no-caps")
                    confirmation.open()

                async def revoke(event) -> None:
                    await confirm_revoke(event.args)

                async def revoke_all(event) -> None:
                    await confirm_revoke(event.args, all_for_user=True)

                table.on("revoke", revoke)
                table.on("revoke_all", revoke_all)
        await load_sessions()

    async def select_dashboard() -> None:
        register_navigation("dashboard", "Dashboard")
        show_authenticated_view()
        state.update(resource="dashboard", rows=[], searched=True, aggregation_detail=None)
        title.text = "Dashboard"
        subtitle.text = "An overview of your records management system"
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        with table_container:
            dashboard_content = ui.column().classes("w-full px-5 pb-5 pt-0 gap-4")

        async def show_unclassified_roots() -> None:
            await select_entity("aggregations")
            try:
                result = await api.search_request("aggregations", {
                    "where": {"and": [
                        {"field": "parent_aggregation_id", "operator": "is_null"},
                        {"field": "classification_id", "operator": "is_null"},
                    ]},
                    "sort": [{"field": "date_created", "direction": "desc"}],
                    "limit": 100,
                })
                state["rows"] = await decorate_for_spec(
                    ENTITIES["aggregations"], result["items"],
                )
                state["searched"] = True
                subtitle.text = "Root aggregations missing a governing classification"
                guidance.text = (
                    f"Showing {len(state['rows'])} of {result['total']} unclassified root aggregations."
                )
                render_table(ENTITIES["aggregations"])
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def load_dashboard() -> None:
            dashboard_content.clear()
            with dashboard_content:
                with ui.row().classes("w-full items-center"):
                    ui.label("System overview").classes("text-lg font-semibold")
                    ui.space()
                    refresh = ui.button("Refresh", icon="refresh").props("flat dense no-caps color=primary")
                loading = ui.row().classes("w-full items-center justify-center py-12 gap-2")
                with loading:
                    ui.spinner("dots", size="32px")
                    ui.label("Loading dashboard…").classes("text-slate-500")

            try:
                privileges = set(auth_state["principal"].get("global_privileges", []))
                can_classify = "classifications.administer" in privileges
                can_organize = "organization.administer" in privileges
                can_administer_users = "identity.users.administer" in privileges

                async def available(value: Any) -> Any:
                    return value

                count_resources = [
                    "aggregations", "records",
                ]
                count_resources += list(dashboard_administration_resources(privileges))
                count_results, scheme_rows, scheme_classification_counts, inactive_result, unclassified_result, favourites, ownership_counts = await asyncio.gather(
                    asyncio.gather(*(api.count(resource) for resource in count_resources)),
                    api.list("classification-schemes") if can_classify else available([]),
                    api.request("GET", "/api/v1/classification-schemes/classification-counts") if can_classify else available([]),
                    api.search_request("classifications", {
                        "where": {"field": "date_deactivated", "operator": "is_not_null"},
                        "limit": 1,
                    }) if can_classify else available({"total": 0}),
                    api.search_request("aggregations", {
                        "where": {"and": [
                            {"field": "parent_aggregation_id", "operator": "is_null"},
                            {"field": "classification_id", "operator": "is_null"},
                        ]},
                        "limit": 1,
                    }),
                    reload_favourites(),
                    api.request("GET", "/api/v1/dashboard/ownership-counts"),
                )
                recent_limit = dashboard_recent_item_limit()
                recent_days = dashboard_recent_days()
                recent_since = datetime.now(timezone.utc) - timedelta(days=recent_days)
                # A dashboard must remain useful while a local API process is
                # being restarted during an upgrade.  Older API processes do
                # not yet expose this optional, self-only activity endpoint;
                # the overview and favourites must not become a "Not Found"
                # page as a result.  Other errors are still surfaced normally.
                try:
                    activity = await api.my_recent_activity(
                        limit=recent_limit, since=recent_since,
                    )
                except ApiError as error:
                    if error.status_code != 404:
                        raise
                    activity = []

                async def activity_rows(entity_type: str, operation: str) -> list[dict[str, Any]]:
                    resource = "aggregations" if entity_type == "aggregation" else "records"
                    entries = [item for item in activity if item["entity_type"] == entity_type
                               and item["operation"] == operation]
                    rows = await asyncio.gather(
                        *(api.get(resource, entry["entity_id"]) for entry in entries),
                        return_exceptions=True,
                    )
                    return [
                        {**row, "_activity_at": entry["occurred_at"]}
                        for entry, row in zip(entries, rows)
                        if isinstance(row, dict)
                    ]

                recent_results = await asyncio.gather(
                    activity_rows("aggregation", "CREATE"),
                    activity_rows("aggregation", "UPDATE"),
                    activity_rows("record", "CREATE"),
                    activity_rows("record", "UPDATE"),
                )
                counts = dict(zip(count_resources, count_results))
                branch_count = sum(int(row["branch_count"]) for row in scheme_classification_counts)
                terminal_count = sum(int(row["terminal_count"]) for row in scheme_classification_counts)
                assignable_terminal_count = sum(
                    int(row["eligible_terminal_count"])
                    for row in scheme_classification_counts
                )
                inactive_classification_count = int(inactive_result["total"])
                unclassified_root_count = int(unclassified_result["total"])
                now = datetime.now(timezone.utc)
                published_scheme_count = 0
                inactive_scheme_count = 0
                draft_scheme_count = 0
                draft_scheme_ids: set[int] = set()
                for scheme in scheme_rows:
                    if scheme.get("date_deactivated"):
                        inactive_scheme_count += 1
                        continue
                    published = scheme.get("date_published")
                    try:
                        published_at = datetime.fromisoformat(
                            str(published).replace("Z", "+00:00")
                        ) if published else None
                    except (TypeError, ValueError):
                        published_at = None
                    if published_at and published_at <= now:
                        published_scheme_count += 1
                    else:
                        draft_scheme_count += 1
                        draft_scheme_ids.add(int(scheme["id"]))
                draft_terminal_count = sum(
                    int(row["terminal_count"])
                    for row in scheme_classification_counts
                    if int(row["classification_scheme_id"]) in draft_scheme_ids
                )
                recent = {
                    "aggregations": (recent_results[0], recent_results[1]),
                    "records": (recent_results[2], recent_results[3]),
                }
                recent = {
                    resource: (
                        await decorate_for_spec(ENTITIES[resource], created),
                        await decorate_for_spec(ENTITIES[resource], updated),
                    )
                    for resource, (created, updated) in recent.items()
                }
                favourite_limit = dashboard_favourite_item_limit()
            except ApiError as error:
                if getattr(page_client, "_deleted", False):
                    return
                if error.status_code == 401:
                    set_connection_status(True)
                    return
                dashboard_content.clear()
                with dashboard_content:
                    ui.label(error_message(error)).classes("text-negative p-5")
                set_connection_status(False)
                return

            if getattr(page_client, "_deleted", False):
                return
            dashboard_content.clear()
            with dashboard_content:
                with ui.row().classes("w-full items-center"):
                    ui.label("System overview").classes("text-lg font-semibold")
                    ui.space()
                    ui.button("Refresh", icon="refresh", on_click=load_dashboard).props("flat dense no-caps color=primary")
                with ui.grid(columns=4).classes("w-full gap-3"):
                    overview_cards = [
                        ("aggregations", "Aggregations", "folder", None, lambda: select_entity("aggregations")),
                        ("records", "Records", "description", None, lambda: select_entity("records")),
                    ]
                    if can_classify:
                        overview_cards.extend((
                            (
                            "classification-schemes", "Classification schemes", "account_tree",
                            f"{published_scheme_count} published · {draft_scheme_count} draft · "
                            f"{inactive_scheme_count} inactive",
                            select_classification_workspace,
                            ), (
                            "classifications", "Classifications", "schema",
                            f"{branch_count} branches · {terminal_count} terminals\n"
                            f"{assignable_terminal_count} assignable terminals · "
                            f"{draft_terminal_count} draft terminals",
                            select_classification_workspace,
                            ),
                        ))
                    if can_organize:
                        overview_cards.extend((
                            ("org-units", "Organization units", "corporate_fare", None, lambda: select_entity("org-units")),
                            ("roles", "Roles", "badge", None, lambda: select_entity("roles")),
                        ))
                    if can_administer_users:
                        overview_cards.append(
                            ("users", "Users", "group", None, lambda: select_entity("users")),
                        )
                    for resource, label, icon, detail, handler in overview_cards:
                        with ui.card().classes("dashboard-stat cursor-pointer p-4 gap-2").on(
                            "click", lambda _, action=handler: action()
                        ):
                            with ui.row().classes("items-center gap-3 no-wrap"):
                                ui.avatar(icon=icon, color="blue-1", text_color="primary")
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(str(counts[resource])).classes("text-2xl font-bold text-slate-800")
                                    ui.label(label).classes("text-xs text-slate-500")
                                    if detail:
                                        ui.label(detail).classes(
                                            "text-[11px] leading-4 text-slate-400 whitespace-pre-line"
                                        )

                ui.label("Holdings by organizational unit").classes("text-lg font-semibold mt-2")
                ui.label(
                    "Shows holdings for organizational units where you currently have an effective "
                    "role. Counts include only aggregations and records you are allowed to view."
                ).classes("text-sm leading-5 text-slate-500 -mt-1")
                if ownership_counts:
                    with ui.card().classes("w-full shadow-none border border-slate-200 p-0 gap-0"):
                        for index, owner_count in enumerate(ownership_counts):
                            if index:
                                ui.separator()
                            with ui.row().classes("w-full items-center gap-3 px-4 py-3"):
                                ui.avatar(
                                    icon="corporate_fare", color="blue-1", text_color="primary",
                                ).props("size=36px")
                                with ui.column().classes("gap-0 grow min-w-0"):
                                    ui.label(
                                        f"{owner_count['org_unit_code']} — "
                                        f"{owner_count['org_unit_name']}"
                                    ).classes("font-semibold text-slate-700")
                                    ui.label(
                                        f"{owner_count['aggregation_count']} aggregations · "
                                        f"{owner_count['record_count']} records"
                                    ).classes("text-xs text-slate-500")
                else:
                    ui.label(
                        "No organizational-unit holdings are available for your effective roles."
                    ).classes("text-sm text-slate-500")

                if unclassified_root_count or inactive_classification_count:
                    ui.label("Governance attention").classes("text-lg font-semibold mt-2")
                    with ui.row().classes("w-full gap-3 flex-wrap"):
                        if unclassified_root_count:
                            with ui.card().classes(
                                "grow min-w-[280px] cursor-pointer shadow-none border "
                                "border-red-200 bg-red-50 p-4"
                            ).on("click", show_unclassified_roots):
                                with ui.row().classes("items-center gap-3 no-wrap"):
                                    ui.avatar(icon="folder_off", color="red-1", text_color="negative")
                                    with ui.column().classes("gap-0"):
                                        ui.label(str(unclassified_root_count)).classes("text-xl font-bold text-negative")
                                        ui.label("Unclassified root aggregations").classes("font-semibold")
                                        ui.label("Root aggregations require a governing classification.").classes("text-xs text-slate-500")
                        if inactive_classification_count:
                            with ui.card().classes(
                                "grow min-w-[280px] cursor-pointer shadow-none border "
                                "border-amber-200 bg-amber-50 p-4"
                            ).on("click", select_classification_workspace):
                                with ui.row().classes("items-center gap-3 no-wrap"):
                                    ui.avatar(icon="label_off", color="amber-1", text_color="amber-9")
                                    with ui.column().classes("gap-0"):
                                        ui.label(str(inactive_classification_count)).classes("text-xl font-bold text-amber-900")
                                        ui.label("Inactive classifications").classes("font-semibold")
                                        ui.label("Unavailable for new aggregation assignments.").classes("text-xs text-slate-500")

                ui.label("Your favourites").classes("text-lg font-semibold mt-2")
                favourites_area = ui.column().classes("w-full gap-3")

                async def open_dashboard_favourite(resource: str, item: dict[str, Any]) -> None:
                    try:
                        entity = await api.get(resource, item["id"])
                        if resource == "aggregations":
                            await open_aggregation(entity)
                        else:
                            decorated = await decorate_for_spec(ENTITIES["records"], [entity])
                            await show_record_details(decorated[0])
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                def render_favourite_entry(
                    resource: str, item: dict[str, Any], *, after_remove: Any,
                ) -> None:
                    icon = "folder" if resource == "aggregations" else "description"
                    with ui.row().classes(
                        "recent-card cursor-pointer w-full items-center no-wrap px-3 py-2 gap-3"
                    ).on(
                        "click",
                        lambda _, selected=item, kind=resource: open_dashboard_favourite(kind, selected),
                    ):
                        ui.icon(icon).classes("text-primary")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                            number = item.get("aggregation_number") or item.get("record_number")
                            ui.label(number).classes("text-xs text-slate-400")
                            if resource == "records":
                                ui.label(
                                    f"{item['aggregation_number']} — {item['aggregation_title']}"
                                ).classes("text-xs text-slate-400 line-clamp-1")
                        remove_button = ui.button(
                            icon="favorite", color="red",
                        ).props("flat round dense aria-label='Remove from favourites'")
                        remove_button.tooltip("Remove from favourites")
                        remove_button.on(
                            "click",
                            lambda _, selected=item, kind=resource: after_remove(kind, selected),
                            js_handler=STOP_PROPAGATION_CLICK_HANDLER,
                        )
                        ui.icon("chevron_right").classes("text-slate-300")

                async def remove_dashboard_favourite(
                    resource: str, item: dict[str, Any], *, dialog_refresh: Any | None = None,
                ) -> None:
                    try:
                        await api.unfavourite(resource, item["id"])
                        favourites[resource] = [
                            entry for entry in favourites[resource]
                            if entry["id"] != item["id"]
                        ]
                        state["favourites"] = favourites
                        state["favourite_ids"][resource].discard(int(item["id"]))
                        render_favourites_dashboard()
                        if dialog_refresh is not None:
                            dialog_refresh()
                        ui.notify("Removed from favourites", color="positive")
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                def show_all_favourites(resource: str) -> None:
                    dialog = ui.dialog()
                    with dialog, ui.card().classes("w-[760px] max-w-full max-h-[85vh]"):
                        with ui.row().classes("w-full items-center"):
                            ui.label(
                                "Favourite aggregations" if resource == "aggregations" else "Favourite records"
                            ).classes("text-xl font-semibold")
                            ui.space()
                            ui.button(icon="close", on_click=dialog.close).props("flat round")
                        complete_list = ui.column().classes("w-full gap-2 max-h-[65vh] overflow-y-auto")

                    def render_complete_list() -> None:
                        complete_list.clear()
                        with complete_list:
                            if not favourites[resource]:
                                ui.label(
                                    "No favourite aggregations" if resource == "aggregations"
                                    else "No favourite records"
                                ).classes("text-sm text-slate-400 py-4")
                            for item in favourites[resource]:
                                render_favourite_entry(
                                    resource, item,
                                    after_remove=lambda kind, selected: remove_dashboard_favourite(
                                        kind, selected, dialog_refresh=render_complete_list,
                                    ),
                                )

                    render_complete_list()
                    dialog.open()

                def render_favourites_dashboard() -> None:
                    favourites_area.clear()
                    with favourites_area:
                        if not favourites["aggregations"] and not favourites["records"]:
                            with ui.card().classes("w-full shadow-none border border-slate-200 p-5"):
                                ui.label(
                                    "You haven't added any favourites yet. Select the heart on an aggregation or record for quick access here."
                                ).classes("text-sm text-slate-500")
                            return
                        with ui.grid(columns=2).classes("w-full gap-5"):
                            for resource, heading, icon, empty_label in (
                                ("aggregations", "Favourite aggregations", "folder", "No favourite aggregations"),
                                ("records", "Favourite records", "description", "No favourite records"),
                            ):
                                with ui.card().classes("w-full shadow-none border border-slate-200 p-4 gap-3"):
                                    with ui.row().classes("w-full items-center gap-2"):
                                        ui.icon(icon, color="primary")
                                        ui.label(heading).classes("font-semibold text-slate-800")
                                        ui.space()
                                        ui.badge(str(len(favourites[resource])), color="blue-grey").props("outline")
                                    preview, has_more = favourite_preview(
                                        favourites[resource], favourite_limit,
                                    )
                                    if not preview:
                                        ui.label(empty_label).classes("text-sm text-slate-400 py-3")
                                    for item in preview:
                                        render_favourite_entry(
                                            resource, item, after_remove=remove_dashboard_favourite,
                                        )
                                    if has_more:
                                        ui.button(
                                            f"View all ({len(favourites[resource])})",
                                            icon="open_in_full",
                                            on_click=lambda _, kind=resource: show_all_favourites(kind),
                                        ).props("flat dense no-caps color=primary").classes("self-end")

                render_favourites_dashboard()

                ui.label("Your recent records activity").classes("text-lg font-semibold mt-2")
                ui.label(
                    f"Created or updated by you during the last {recent_days} days"
                ).classes("text-sm text-slate-500 -mt-4")
                with ui.grid(columns=2).classes("w-full gap-5"):
                    for resource, singular, icon in (
                        ("aggregations", "aggregation", "folder"),
                        ("records", "record", "description"),
                    ):
                        with ui.card().classes("w-full shadow-none border border-slate-200 p-4 gap-4"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon(icon, color="primary")
                                ui.label(ENTITIES[resource].label).classes("font-semibold text-slate-800")
                            for heading, items, activity_icon in (
                                ("Recently created by you", recent[resource][0], "add_circle"),
                                ("Recently updated by you", recent[resource][1], "history"),
                            ):
                                ui.label(heading).classes("component-meta-label mt-1")
                                if not items:
                                    ui.label("Nothing here yet").classes("text-sm text-slate-400")
                                for item in items:
                                    handler = (
                                        (lambda _, entry=item: open_aggregation(entry))
                                        if resource == "aggregations"
                                        else (lambda _, entry=item: show_record_details(entry))
                                    )
                                    with ui.row().classes(
                                        "recent-card cursor-pointer w-full items-center no-wrap px-3 py-2 gap-3"
                                    ).on("click", handler):
                                        ui.icon(icon).classes("text-primary")
                                        with ui.column().classes("gap-0 grow min-w-0"):
                                            ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                                            number = item.get("aggregation_number") or item.get("record_number")
                                            ui.label(number).classes("text-xs text-slate-400")
                                        ui.label(format_timestamp(item.get("_activity_at"))).classes("text-xs text-slate-400")
                                        ui.icon("chevron_right").classes("text-slate-300")
                set_connection_status(True)

        await load_dashboard()

    async def select_audit_trail() -> None:
        register_navigation("audit-trail", "Audit trail")
        show_authenticated_view()
        state.update(resource="audit-trail", rows=[], searched=True, aggregation_detail=None)
        title.text = "Audit trail"
        subtitle.text = "Immutable history of changes across the system"
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        with table_container:
            with ui.column().classes("w-full p-5 gap-4"):
                with ui.card().classes("w-full shadow-none border border-slate-200 p-4"):
                    ui.label("Filter events").classes("font-semibold")
                    with ui.grid(columns=4).classes("w-full gap-3"):
                        type_filter = ui.select(
                            {}, label="Entity type", clearable=True,
                        ).props("outlined dense use-input options-dense").classes("w-full")
                        operation_filter = ui.select(
                            [],
                            label="Operation", clearable=True,
                        ).props("outlined dense use-input options-dense").classes("w-full")
                        source_filter = ui.select(
                            [], label="Source", clearable=True,
                        ).props("outlined dense use-input options-dense").classes("w-full")
                        actor_filter = ui.select(
                            [], label="Actor type", clearable=True,
                        ).props("outlined dense use-input options-dense").classes("w-full")
                        from_filter = ui.input("From").props("outlined dense type=datetime-local").classes("w-full")
                        until_filter = ui.input("Until").props("outlined dense type=datetime-local").classes("w-full")
                        entity_id_filter = ui.number("Entity ID", min=1, format="%.0f").props("outlined dense clearable").classes("w-full")
                        correlation_filter = ui.input("Correlation ID").props("outlined dense clearable").classes("w-full")
                    with ui.row().classes("w-full justify-end"):
                        refresh_button = ui.button("Apply filters", icon="filter_alt").props("unelevated no-caps")
                with ui.row().classes("w-full items-center gap-2"):
                    result_summary = ui.label().classes("text-sm text-slate-500 grow")
                    previous_button = ui.button("Previous", icon="chevron_left").props("flat dense no-caps")
                    next_button = ui.button("Next", icon="chevron_right").props("flat dense no-caps")
                    previous_button.disable()
                    next_button.disable()
                results_container = ui.column().classes("w-full gap-2")

        page = {"offset": 0, "size": 50, "total": 0}

        try:
            filter_options = await api.event_history_filter_options()
            type_filter.options = {
                value: value.replace("_", " ").title()
                for value in filter_options["entity_types"]
            }
            operation_filter.options = filter_options["operations"]
            source_filter.options = filter_options["sources"]
            actor_filter.options = filter_options["actor_types"]
            for control in (
                type_filter, operation_filter, source_filter, actor_filter,
            ):
                control.update()
        except ApiError as error:
            if error.status_code != 401:
                ui.notify(
                    f"Could not load audit operation filters: {error_message(error)}",
                    color="warning",
                    close_button=True,
                )

        async def load_audit_events() -> None:
            refresh_button.props("loading disable")
            conditions: list[dict[str, Any]] = []
            for field, operator, value in (
                ("entity_type", "eq", type_filter.value),
                ("operation", "eq", operation_filter.value),
                ("source", "eq", source_filter.value),
                ("actor_type", "eq", actor_filter.value),
                ("entity_id", "eq", int(entity_id_filter.value) if entity_id_filter.value else None),
                ("correlation_id", "eq", (correlation_filter.value or "").strip()),
                ("occurred_at", "gte", from_filter.value),
                ("occurred_at", "lte", until_filter.value),
            ):
                if value not in (None, ""):
                    conditions.append({"field": field, "operator": operator, "value": value})
            payload: dict[str, Any] = {
                "sort": [{"field": "occurred_at", "direction": "desc"}, {"field": "id", "direction": "desc"}],
                "limit": page["size"], "offset": page["offset"],
            }
            if conditions:
                payload["where"] = conditions[0] if len(conditions) == 1 else {"and": conditions}
            try:
                response = await api.search_request("event-history", payload)
                events_list = response["items"]
                hydrate_historical_audit_identities(events_list)
                page["total"] = response["total"]
                first = page["offset"] + 1 if events_list else 0
                last = page["offset"] + len(events_list)
                result_summary.text = f"Showing {first}–{last} of {page['total']} matching events"
                if page["offset"] > 0:
                    previous_button.enable()
                else:
                    previous_button.disable()
                if last < page["total"]:
                    next_button.enable()
                else:
                    next_button.disable()
                render_event_timeline(events_list, results_container)
                set_connection_status(True)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
            finally:
                refresh_button.props(remove="loading disable")

        async def apply_filters() -> None:
            page["offset"] = 0
            await load_audit_events()

        async def previous_page() -> None:
            page["offset"] = max(0, page["offset"] - page["size"])
            await load_audit_events()

        async def next_page() -> None:
            if page["offset"] + page["size"] < page["total"]:
                page["offset"] += page["size"]
                await load_audit_events()

        refresh_button.on("click", apply_filters)
        previous_button.on("click", previous_page)
        next_button.on("click", next_page)
        await load_audit_events()

    async def load_rows(*, repeat_search: bool = False) -> None:
        spec = ENTITIES[state["resource"]]
        try:
            if spec.search_first:
                query = (search_input.value or "").strip()
                if not query and not repeat_search:
                    state["searched"] = False
                    state["rows"] = []
                elif query:
                    rows = await api.search(spec.key, query, spec.search_fields)
                    state["rows"] = await decorate_for_spec(spec, rows)
                    state["searched"] = True
            else:
                rows = await api.list(spec.key)
                state["rows"] = await decorate_for_spec(spec, rows)
                state["searched"] = True
            set_connection_status(True)
            render_table(spec)
        except ApiError as error:
            if getattr(page_client, "_deleted", False):
                return
            set_connection_status(error.status_code != 503)
            ui.notify(error_message(error), color="negative", close_button=True)

    def set_aggregation_mode_controls(mode: str) -> None:
        for button, active in (
            (aggregation_search_mode, mode == "search"),
            (aggregation_browse_mode, mode == "browse"),
        ):
            button.props(remove="flat unelevated")
            button.props("unelevated" if active else "flat")

    async def select_aggregation_browser() -> None:
        state["aggregation_mode"] = "browse"
        state["aggregation_detail"] = None
        set_aggregation_mode_controls("browse")
        search_bar.set_visibility(False)
        guidance.text = "Browse published classification schemes, governed aggregations, and their records."
        add_button.set_visibility(key != "privileges")
        add_button.text = "Add"
        add_button.update()
        add_record_button.set_visibility(False)
        table_container.clear()

        browse: dict[str, Any] = state.setdefault("aggregation_browse", {
            "schemes": [], "scheme_id": None, "collections": {},
            "expanded": set(), "selected": None, "selected_item": None,
            "revision": 0,
        })

        def collection_key(kind: str, owner_id: int, collection: str) -> str:
            return f"{kind}:{owner_id}:{collection}"

        def collection_state(key: str, path: str) -> dict[str, Any]:
            return browse["collections"].setdefault(key, {
                "path": path, "items": [], "next_cursor": None, "total": 0,
                "loaded": False, "loading": False, "error": None, "query": "",
                "request_version": 0,
            })

        tree_panel: Any = None
        detail_panel: Any = None
        scheme_select: Any = None

        async def render_tree_preserving_scroll(*, anchor_id: str | None = None) -> None:
            anchor_expression = (
                f"document.getElementById('{anchor_id}')?.getBoundingClientRect().top ?? null"
                if anchor_id else "null"
            )
            scroll_position = await page_client.run_javascript(
                "({ page: window.scrollY || 0, "
                "tree: document.getElementById('aggregation-browser-tree')?.scrollTop || 0, "
                f"anchor: {anchor_expression} }})"
            )
            render_tree()
            anchor_top = (scroll_position or {}).get("anchor")
            anchor_top_javascript = "null" if anchor_top is None else str(float(anchor_top))
            anchor_restore = (
                f"const anchor = document.getElementById('{anchor_id}'); "
                f"if (anchor && {anchor_top_javascript} !== null) "
                f"tree.scrollTop += anchor.getBoundingClientRect().top - {float(anchor_top or 0)}; "
                if anchor_id else ""
            )
            await page_client.run_javascript(
                "requestAnimationFrame(() => requestAnimationFrame(() => { "
                "const tree = document.getElementById('aggregation-browser-tree'); "
                f"if (tree) tree.scrollTop = {float((scroll_position or {}).get('tree', 0))}; "
                f"if (tree) {{ {anchor_restore} }} "
                f"window.scrollTo(0, {float((scroll_position or {}).get('page', 0))}); "
                "}));"
            )

        async def restore_page_scroll(scroll_top: float | int | None) -> None:
            await page_client.run_javascript(
                "requestAnimationFrame(() => requestAnimationFrame(() => "
                f"window.scrollTo(0, {float(scroll_top or 0)})));"
            )

        def render_detail_content(
            item: dict[str, Any] | None, retention: dict[str, Any] | None = None,
            *, loading_retention: bool = False,
        ) -> None:
            detail_panel.clear()
            with detail_panel:
                def detail_value(label: str, value: Any, *, timestamp: bool = False) -> None:
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(label.upper()).classes("component-meta-label")
                        ui.label(
                            format_timestamp(value) if timestamp else display_value(value)
                        ).classes("text-sm text-slate-700")

                if item is None:
                    with ui.column().classes("w-full h-full items-center justify-center gap-2 text-slate-400"):
                        ui.icon("touch_app", size="42px")
                        ui.label("Select an aggregation or record to see its details.")
                    return
                is_aggregation = item["type"] == "aggregation"
                icon = "folder" if is_aggregation else "description"
                number = item["aggregation_number"] if is_aggregation else item["record_number"]
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    ui.avatar(icon=icon, color="blue-1", text_color="primary")
                    with ui.column().classes("grow min-w-0 gap-0"):
                        ui.label(item["title"]).classes("text-xl font-semibold whitespace-normal")
                        ui.label(number).classes("text-sm font-medium text-primary")
                    if is_aggregation and item.get("date_closed"):
                        ui.badge("Closed", color="amber-8").props("outline")
                if item.get("description"):
                    ui.label(item["description"]).classes(
                        "w-full max-h-28 overflow-y-auto rounded-lg bg-slate-50 p-3 "
                        "text-sm leading-6 text-slate-600 whitespace-pre-wrap"
                    )
                with ui.grid(columns=2).classes("w-full gap-3"):
                    if is_aggregation:
                        detail_value("Created", item.get("date_created"), timestamp=True)
                        detail_value("Opened", item.get("date_opened"), timestamp=True)
                        detail_value("Child aggregations", item.get("child_aggregation_count", 0))
                        detail_value("Records", item.get("record_count", 0))
                        if item.get("classification_code"):
                            detail_value(
                                "Classification",
                                f"{item['classification_code']} — {item['classification_title']}",
                            )
                    else:
                        detail_value("Originated", item.get("date_originated"), timestamp=True)
                        detail_value("Created", item.get("date_created"), timestamp=True)
                        detail_value("Digital components", item.get("digital_component_count", 0))
                        detail_value(
                            "Containing aggregation",
                            f"{item['aggregation_number']} — {item['aggregation_title']}",
                        )
                if is_aggregation:
                    ui.separator()
                    ui.label("Effective retention rule").classes("font-semibold")
                    if loading_retention:
                        with ui.row().classes("items-center gap-2 text-sm text-slate-500"):
                            ui.spinner("dots", size="20px")
                            ui.label("Loading retention information…")
                    elif retention:
                        source = "Local aggregation override" if retention.get("rule_source") == "aggregation" else "Inherited from classification"
                        ui.label(source).classes("text-xs font-medium text-indigo-700")
                        with ui.row().classes("w-full gap-4 text-sm"):
                            ui.label(f"Current: {retention['current_period_years']} years")
                            ui.label(f"Intermediate: {retention['intermediate_period_years']} years")
                        ui.badge(
                            retention["final_disposition"].replace("_", " ").title(),
                            color="indigo",
                        ).props("outline")
                    else:
                        ui.label("No effective retention rule is available.").classes("text-sm text-slate-400")

                async def open_selected() -> None:
                    try:
                        if is_aggregation:
                            await open_aggregation(await api.get("aggregations", item["id"]))
                        else:
                            await show_record_details(await api.get("records", item["id"]))
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end mt-auto"):
                    ui.button(
                        "Open aggregation" if is_aggregation else "Open record",
                        icon="open_in_new", on_click=open_selected,
                    ).props("unelevated no-caps color=primary")

        async def select_browse_item(item: dict[str, Any]) -> None:
            page_scroll_top = await page_client.run_javascript("window.scrollY || 0")
            browse["selected"] = (item["type"], item["id"])
            browse["selected_item"] = item
            render_detail_content(item, loading_retention=item["type"] == "aggregation")
            await restore_page_scroll(page_scroll_top)
            if item["type"] == "aggregation":
                try:
                    retention = await api.effective_retention_rule(item["id"])
                except ApiError as error:
                    retention = None
                    if error.status_code not in {404, 409}:
                        ui.notify(error_message(error), color="negative", close_button=True)
                if browse.get("selected") == (item["type"], item["id"]):
                    render_detail_content(item, retention)
                    await restore_page_scroll(page_scroll_top)

        async def load_collection(
            key: str, *, append: bool = False, render: bool = True,
        ) -> None:
            current = browse["collections"].get(key)
            if current is None or current["loading"]:
                return
            append_anchor_id = (
                browse_item_dom_id(current["items"][-1])
                if append and current["items"] else None
            )
            browse["revision"] += 1
            current["request_version"] += 1
            request_version = current["request_version"]
            current["loading"] = True
            current["error"] = None
            if render:
                await render_tree_preserving_scroll()
            try:
                result = await api.browse_page(
                    current["path"],
                    cursor=current["next_cursor"] if append else None,
                    query=current["query"],
                )
                if (
                    current["request_version"] != request_version
                    or browse["collections"].get(key) is not current
                ):
                    return
                existing = {entry["id"] for entry in current["items"]} if append else set()
                additions = [entry for entry in result["items"] if entry["id"] not in existing]
                current["items"] = [*current["items"], *additions] if append else additions
                current["next_cursor"] = result.get("next_cursor")
                current["total"] = int(result["total"])
                current["loaded"] = True
            except ApiError as error:
                if current["request_version"] == request_version:
                    current["error"] = error_message(error)
            finally:
                if current["request_version"] == request_version:
                    current["loading"] = False
                    if render:
                        await render_tree_preserving_scroll(anchor_id=append_anchor_id)

        def browse_item_dom_id(item: dict[str, Any]) -> str:
            if "is_terminal" in item:
                kind = "classification"
            elif "aggregation_number" in item:
                kind = "aggregation"
            else:
                kind = "record"
            return f"aggregation-browser-{kind}-{int(item['id'])}"

        async def filter_collection(key: str, value: str) -> None:
            current = browse["collections"][key]
            current["request_version"] += 1
            current.update(
                items=[], next_cursor=None, total=0, loaded=False,
                loading=False, error=None, query=value.strip(),
            )
            await load_collection(key)

        def render_collection_controls(key: str, noun: str) -> None:
            current = browse["collections"][key]
            if current["total"] <= 50 and not current["query"]:
                return
            with ui.row().classes("w-full items-center gap-1 py-1"):
                filter_input = ui.input(
                    f"Filter {noun}", value=current["query"],
                ).props("outlined dense clearable").classes("grow")
                ui.button(
                    icon="search", on_click=lambda: filter_collection(key, filter_input.value or ""),
                ).props("flat round dense color=primary").tooltip(f"Filter these {noun}")
                filter_input.on(
                    "keydown.enter", lambda: filter_collection(key, filter_input.value or "")
                )

        def render_continuation(key: str, noun: str, depth: int) -> None:
            current = browse["collections"][key]
            if not current.get("next_cursor"):
                return
            remaining = max(0, current["total"] - len(current["items"]))
            amount = min(50, remaining)
            with ui.button(
                on_click=lambda: load_collection(key, append=True), icon="more_horiz",
            ).props("flat dense no-caps color=primary").classes("w-full justify-start").style(
                f"padding-left: {depth * 20 + 36}px"
            ):
                ui.label(
                    f"Load {amount} more {noun} · {len(current['items'])} of {current['total']}"
                ).classes("text-xs")

        def render_collection_status(key: str, empty_text: str, depth: int) -> bool:
            current = browse["collections"][key]
            if current["loading"] and not current["items"]:
                with ui.row().classes("items-center gap-2 py-2 text-slate-400").style(
                    f"padding-left: {depth * 20 + 36}px"
                ):
                    ui.spinner("dots", size="20px")
                    ui.label("Loading…").classes("text-xs")
                return True
            if current["error"]:
                with ui.row().classes("items-center gap-2 py-2 text-negative").style(
                    f"padding-left: {depth * 20 + 36}px"
                ):
                    ui.label(current["error"]).classes("text-xs")
                    ui.button("Retry", on_click=lambda: load_collection(key)).props(
                        "flat dense no-caps color=negative"
                    )
                return True
            if current["loaded"] and not current["items"]:
                ui.label(empty_text).classes("text-xs text-slate-400 py-2").style(
                    f"padding-left: {depth * 20 + 36}px"
                )
                return True
            return False

        async def toggle_classification(item: dict[str, Any]) -> None:
            node = ("classification", item["id"])
            if node in browse["expanded"]:
                browse["expanded"].remove(node)
                await render_tree_preserving_scroll()
                return
            browse["expanded"].add(node)
            collection = "aggregations" if item["is_terminal"] else "classifications"
            path = (
                f"classifications/{item['id']}/aggregations"
                if item["is_terminal"] else f"classifications/{item['id']}/children"
            )
            key = collection_key("classification", item["id"], collection)
            current = collection_state(key, path)
            if not current["loaded"]:
                await load_collection(key)
            else:
                await render_tree_preserving_scroll()

        async def toggle_aggregation(item: dict[str, Any]) -> None:
            node = ("aggregation", item["id"])
            if node in browse["expanded"]:
                browse["expanded"].remove(node)
                await render_tree_preserving_scroll()
                return
            browse["expanded"].add(node)
            child_key = collection_key("aggregation", item["id"], "aggregations")
            record_key = collection_key("aggregation", item["id"], "records")
            child_state = collection_state(
                child_key, f"aggregations/{item['id']}/children",
            )
            record_state = collection_state(
                record_key, f"aggregations/{item['id']}/records",
            )
            await render_tree_preserving_scroll()
            await asyncio.gather(*(
                load_collection(key, render=False)
                for key, value in ((child_key, child_state), (record_key, record_state))
                if not value["loaded"]
            ))
            await render_tree_preserving_scroll()

        def render_classification(item: dict[str, Any], depth: int) -> None:
            node = ("classification", item["id"])
            expanded = node in browse["expanded"]
            with ui.row().props(f"id={browse_item_dom_id(item)}").classes(
                "w-full items-center no-wrap rounded-lg py-1 pr-2 hover:bg-blue-50"
            ).style(f"padding-left: {depth * 20 + 4}px"):
                ui.button(
                    icon="expand_more" if expanded else "chevron_right",
                    on_click=lambda: toggle_classification(item),
                ).props("flat round dense size=sm color=blue-grey")
                ui.icon("label" if item["is_terminal"] else "schema", color="primary").classes("w-6")
                with ui.column().classes("grow min-w-0 gap-0"):
                    ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                    ui.label(item["code"]).classes("text-xs text-slate-400")
                ui.badge("Terminal" if item["is_terminal"] else "Branch", color="primary").props("outline")
            if not expanded:
                return
            collection = "aggregations" if item["is_terminal"] else "classifications"
            key = collection_key("classification", item["id"], collection)
            current = browse["collections"].get(key)
            if current is None or render_collection_status(
                key,
                "No governed aggregations" if item["is_terminal"] else "No child classifications",
                depth + 1,
            ):
                return
            render_collection_controls(key, "aggregations" if item["is_terminal"] else "classifications")
            for child in current["items"]:
                if item["is_terminal"]:
                    render_aggregation(child, depth + 1)
                else:
                    render_classification(child, depth + 1)
            render_continuation(
                key, "aggregations" if item["is_terminal"] else "classifications", depth + 1,
            )

        def render_aggregation(item: dict[str, Any], depth: int) -> None:
            item["type"] = "aggregation"
            node = ("aggregation", item["id"])
            expanded = node in browse["expanded"]
            selected = browse["selected"] == node
            with ui.row().props(f"id={browse_item_dom_id(item)}").classes(
                "w-full items-center no-wrap rounded-lg py-1 pr-2 hover:bg-blue-50 "
                + ("bg-blue-50" if selected else "")
            ).style(f"padding-left: {depth * 20 + 4}px"):
                has_content = item["child_aggregation_count"] or item["record_count"]
                with ui.element("div").classes("w-8 shrink-0"):
                    if has_content:
                        ui.button(
                            icon="expand_more" if expanded else "chevron_right",
                            on_click=lambda: toggle_aggregation(item),
                        ).props("flat round dense size=sm color=blue-grey")
                ui.icon("folder", color="primary").classes("w-6")
                with ui.column().classes("grow min-w-0 gap-0 cursor-pointer").on(
                    "click", lambda: select_browse_item(item)
                ):
                    ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                    ui.label(item["aggregation_number"]).classes("text-xs text-slate-400")
                if item.get("date_closed"):
                    ui.badge("Closed", color="amber-8").props("outline")
            if not expanded:
                return
            for collection, heading, noun, empty in (
                ("aggregations", "CHILD AGGREGATIONS", "child aggregations", "No child aggregations"),
                ("records", "RECORDS", "records", "No records in this aggregation"),
            ):
                count = item["child_aggregation_count"] if collection == "aggregations" else item["record_count"]
                if not count:
                    continue
                key = collection_key("aggregation", item["id"], collection)
                ui.label(f"{heading}  ·  {count}").classes(
                    "text-[10px] font-semibold tracking-wider text-slate-400 py-1"
                ).style(f"padding-left: {(depth + 1) * 20 + 36}px")
                if render_collection_status(key, empty, depth + 1):
                    continue
                render_collection_controls(key, noun)
                current = browse["collections"][key]
                for child in current["items"]:
                    if collection == "aggregations":
                        render_aggregation(child, depth + 1)
                    else:
                        render_record(child, depth + 1)
                render_continuation(key, noun, depth + 1)

        def render_record(item: dict[str, Any], depth: int) -> None:
            item["type"] = "record"
            selected = browse["selected"] == ("record", item["id"])
            with ui.row().props(f"id={browse_item_dom_id(item)}").classes(
                "w-full items-center no-wrap rounded-lg py-2 pr-2 hover:bg-blue-50 cursor-pointer "
                + ("bg-blue-50" if selected else "")
            ).style(f"padding-left: {depth * 20 + 40}px").on(
                "click", lambda: select_browse_item(item)
            ):
                ui.icon("description", color="blue-grey").classes("w-6")
                with ui.column().classes("grow min-w-0 gap-0"):
                    ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                    ui.label(item["record_number"]).classes("text-xs text-slate-400")
                if item["digital_component_count"]:
                    ui.badge(str(item["digital_component_count"]), color="blue-grey").props("outline")

        def render_tree() -> None:
            tree_panel.clear()
            with tree_panel:
                scheme_id = browse["scheme_id"]
                if scheme_id is None:
                    ui.label("Choose a classification scheme to begin browsing.").classes(
                        "text-sm text-slate-400 py-10 self-center"
                    )
                    return
                key = collection_key("scheme", scheme_id, "classifications")
                if key not in browse["collections"]:
                    return
                if render_collection_status(key, "This scheme has no root classifications", 0):
                    return
                current = browse["collections"][key]
                render_collection_controls(key, "classifications")
                for item in current["items"]:
                    render_classification(item, 0)
                render_continuation(key, "classifications", 0)

        async def select_browse_scheme(scheme_id: int | None) -> None:
            if scheme_id is None:
                return
            browse["revision"] += 1
            browse.update(
                scheme_id=int(scheme_id), collections={}, expanded=set(),
                selected=None, selected_item=None,
            )
            render_detail_content(None)
            key = collection_key("scheme", int(scheme_id), "classifications")
            collection_state(key, f"classification-schemes/{scheme_id}/roots")
            await load_collection(key)

        with table_container:
            with ui.row().classes("w-full items-end gap-3 px-5 pt-5"):
                scheme_select = ui.select(
                    {}, label="Classification scheme",
                ).props("outlined dense options-dense").classes("grow")
                ui.button(
                    icon="refresh",
                    on_click=lambda: select_browse_scheme(browse["scheme_id"]),
                ).props("flat round color=primary").tooltip("Refresh the hierarchy")
            with ui.grid(columns=2).classes("w-full h-[680px] min-h-0 gap-0 p-5 pt-3"):
                with ui.card().classes(
                    "w-full h-full min-h-0 overflow-hidden shadow-none border border-slate-200 p-0"
                ):
                    with ui.row().classes("w-full items-center px-4 py-3 border-b border-slate-200"):
                        ui.icon("account_tree", color="primary")
                        ui.label("Classification, aggregation and record tree").classes("font-semibold")
                    tree_panel = ui.column().props("id=aggregation-browser-tree").classes(
                        "w-full grow min-h-0 gap-0 overflow-y-auto p-2"
                    )
                detail_panel = ui.column().classes(
                    "w-full h-full min-h-0 overflow-y-auto border border-l-0 border-slate-200 p-5 gap-4"
                )
            with ui.expansion(
                "Recent aggregation activity", icon="history",
            ).classes("w-full border-t border-slate-200"):
                with ui.row().classes("w-full p-4 gap-5 items-start"):
                    for heading, rows in (
                        ("Recently created", state["recent_created"]),
                        ("Recently updated", state["recent_updated"]),
                    ):
                        with ui.column().classes("grow min-w-[280px] gap-2"):
                            ui.label(heading).classes("text-sm font-semibold text-slate-600")
                            if not rows:
                                ui.label("Nothing here yet").classes("text-xs text-slate-400")
                            for recent in rows:
                                with ui.row().classes(
                                    "w-full items-center gap-2 rounded-lg border border-slate-200 "
                                    "px-3 py-2 cursor-pointer hover:bg-blue-50"
                                ).on("click", lambda _, entry=recent: open_aggregation(entry)):
                                    ui.icon("folder", color="primary", size="18px")
                                    with ui.column().classes("grow min-w-0 gap-0"):
                                        ui.label(recent["title"]).classes("text-sm font-semibold truncate")
                                        ui.label(recent["aggregation_number"]).classes("text-xs text-slate-400")

        render_detail_content(None)
        try:
            browse["schemes"] = await api.browse_schemes()
            scheme_select.options = {
                item["id"]: (
                    f"{item['code']} — {item['title']}"
                    + (" · Inactive" if item.get("date_deactivated") else "")
                ) for item in browse["schemes"]
            }
            scheme_select.update()
            if browse["schemes"]:
                available_ids = {item["id"] for item in browse["schemes"]}
                target_scheme_id = (
                    browse["scheme_id"]
                    if browse["scheme_id"] in available_ids
                    else browse["schemes"][0]["id"]
                )
                scheme_select.value = target_scheme_id
                scheme_select.update()
                root_key = collection_key("scheme", target_scheme_id, "classifications")
                if root_key in browse["collections"] and browse["collections"][root_key]["loaded"]:
                    render_tree()
                    if browse.get("selected_item"):
                        await select_browse_item(browse["selected_item"])
                else:
                    await select_browse_scheme(target_scheme_id)
            else:
                render_tree()
        except ApiError as error:
            with tree_panel:
                ui.label(error_message(error)).classes("text-negative p-4")
        scheme_select.on_value_change(lambda event: select_browse_scheme(event.value))

    async def select_aggregation_search() -> None:
        state["aggregation_mode"] = "search"
        set_aggregation_mode_controls("search")
        search_bar.set_visibility(True)
        guidance.text = "Large collections are search-first to avoid loading unbounded result sets."
        render_table(ENTITIES["aggregations"])

    async def confirm_identity_deletion(
        resource: str, item: dict[str, Any], *, label: str, on_deleted: Callable[[], Any],
    ) -> None:
        """Explain the server's deletion analysis and require a reason."""
        try:
            report = await api.deletion_preflight(resource, item["id"])
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        dialog = ui.dialog().props("persistent")
        with dialog, ui.card().classes("w-[620px] max-w-full gap-4 p-5"):
            ui.label(f"Permanently delete {label}?").classes("text-xl font-semibold")
            ui.label(item.get("name") or item.get("code") or str(item["id"])).classes("font-medium")
            if report["blockers"]:
                ui.label("Deletion is currently blocked").classes("text-negative font-semibold")
                for blocker in report["blockers"]:
                    with ui.row().classes("items-start gap-2"):
                        ui.icon("block", color="negative").classes("mt-0.5")
                        with ui.column().classes("gap-0 grow"):
                            ui.label(blocker["message"]).classes("text-sm")
                            details = blocker.get("details") or {}
                            if details:
                                ui.label(" · ".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in details.items())).classes("text-xs text-slate-500")
                ui.label("Resolve every blocker and run the preflight again. There is no force-delete override.").classes("text-xs text-slate-500")
                ui.button("Close", on_click=dialog.close).props("flat no-caps").classes("self-end")
            else:
                cascades = {key: value for key, value in report.get("cascades", {}).items() if value}
                ui.label("The live entity cannot be restored. Immutable audit history will remain.").classes("text-sm text-slate-600")
                if cascades:
                    ui.label("Data removed automatically").classes("text-sm font-semibold")
                    ui.label(" · ".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in cascades.items())).classes("text-sm text-slate-600")
                reason = ui.textarea("Reason for permanent deletion").props("outlined autogrow counter maxlength=2000").classes("w-full")

                async def remove() -> None:
                    change_reason = (reason.value or "").strip()
                    if not change_reason:
                        ui.notify("A deletion reason is required", color="warning")
                        return
                    try:
                        await api.delete(resource, item["id"], report["entity_version"], reason=change_reason)
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                        dialog.close()
                        return
                    dialog.close()
                    ui.notify(f"{label.title()} permanently deleted", color="positive")
                    result = on_deleted()
                    if inspect.isawaitable(result):
                        await result

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Delete permanently", icon="delete_forever", color="negative", on_click=remove).props("unelevated no-caps")
        dialog.open()

    async def select_organization_unit_details(org_unit_id: int) -> None:
        register_navigation("org-unit-details", f"Organization unit #{org_unit_id}", entity_id=org_unit_id)
        show_authenticated_view()
        state.update(resource="org-unit-details", rows=[], searched=True, aggregation_detail=None)
        search_bar.set_visibility(False); aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False); add_record_button.set_visibility(False)
        guidance.text = ""; table_container.clear()
        try:
            unit = await api.organization_summary("org-units", org_unit_id)
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True); return
        title.text = unit["name"]; subtitle.text = "Organization unit details and inherited lifecycle effects"
        register_navigation(
            "org-unit-details", unit["name"], entity_id=org_unit_id,
            accessible_label=f"{unit['name']} — {unit['code']}",
        )

        async def refresh(_: Any = None) -> None:
            await select_organization_unit_details(org_unit_id)

        async def change_status() -> None:
            try:
                await api.set_active(
                    "org-units", org_unit_id, unit["version"],
                    active=unit["status"] == "inactive",
                )
                await refresh()
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        with table_container, ui.column().classes("w-full p-5 gap-4"):
            with ui.card().classes("w-full shadow-none border border-slate-200 p-5 gap-4"):
                with ui.row().classes("w-full items-start gap-4"):
                    ui.avatar(icon="corporate_fare", color="blue-1", text_color="primary", size="58px")
                    with ui.column().classes("gap-1 grow"):
                        ui.label(unit["name"]).classes("text-xl font-semibold")
                        ui.label(unit["code"]).classes("text-primary")
                        if unit.get("description"): ui.label(unit["description"]).classes("text-slate-600")
                    ui.button(
                        "Back", icon="arrow_back",
                        on_click=lambda: breadcrumb_back(lambda: select_entity("org-units")),
                    ).props("flat no-caps")
                    ui.button("Edit", icon="edit", on_click=lambda: open_editor(unit, on_saved=refresh, resource_key="org-units")).props("flat no-caps")
                    ui.button("History", icon="history", on_click=lambda: show_entity_history("org-units", unit)).props("flat no-caps")
                    ui.button("Activate" if unit["status"] == "inactive" else "Deactivate", icon="toggle_on" if unit["status"] == "inactive" else "toggle_off", on_click=change_status).props("outline no-caps")
                    ui.button(
                        "Delete", icon="delete_outline", color="negative",
                        on_click=lambda: confirm_identity_deletion(
                            "org-units", unit, label="organization unit",
                            on_deleted=lambda: select_entity("org-units"),
                        ),
                    ).props("flat no-caps")
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for label, value in (
                        ("Direct status", unit.get("status")), ("Effective status", unit.get("effective_status")),
                        ("Inactive because of", (unit.get("inactive_source") or {}).get("name")),
                        ("Parent", (unit.get("parent") or {}).get("name")),
                        ("Direct child units", unit.get("child_org_unit_count")),
                        ("Direct roles", unit.get("role_count")),
                    ):
                        guidance_text = {
                            "Direct status": "Set directly on this organization unit, without considering parent units.",
                            "Effective status": "Also includes inactivity inherited from any parent organization unit.",
                        }.get(label)
                        with ui.column().classes("gap-0 border-b border-slate-100 pb-1.5"):
                            ui.label(label.upper()).classes("text-xs text-slate-400")
                            ui.label(str(value).title() if value is not None else "—").classes("font-medium")
                            if guidance_text:
                                ui.label(guidance_text).classes("w-full text-[10px] leading-3 text-slate-400")

    async def select_role_details(role_id: int) -> None:
        register_navigation("role-details", f"Role #{role_id}", entity_id=role_id)
        show_authenticated_view()
        state.update(resource="role-details", rows=[], searched=True, aggregation_detail=None)
        search_bar.set_visibility(False); aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False); add_record_button.set_visibility(False)
        guidance.text = ""; table_container.clear()
        try:
            role = await api.organization_summary("roles", role_id)
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True); return
        title.text = role["name"]; subtitle.text = "Role details, assignments, supervision, and inherited lifecycle effects"
        register_navigation(
            "role-details", role["name"], entity_id=role_id,
            accessible_label=f"{role['name']} — {role['code']}",
        )

        async def refresh(_: Any = None) -> None:
            await select_role_details(role_id)

        async def change_status() -> None:
            try:
                await api.set_active("roles", role_id, role["version"], active=role["status"] == "inactive")
                await refresh()
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        with table_container, ui.column().classes("w-full p-5 gap-4"):
            with ui.card().classes("w-full shadow-none border border-slate-200 p-5 gap-4"):
                with ui.row().classes("w-full items-start gap-4"):
                    ui.avatar(icon="badge", color="blue-1", text_color="primary", size="58px")
                    with ui.column().classes("gap-1 grow"):
                        ui.label(role["name"]).classes("text-xl font-semibold")
                        ui.label(role["code"]).classes("text-primary")
                        if role.get("description"): ui.label(role["description"]).classes("text-slate-600")
                    ui.button(
                        "Back", icon="arrow_back",
                        on_click=lambda: breadcrumb_back(lambda: select_entity("roles")),
                    ).props("flat no-caps")
                    ui.button("Edit", icon="edit", on_click=lambda: open_editor(role, on_saved=refresh, resource_key="roles")).props("flat no-caps")
                    ui.button("User assignments", icon="group", on_click=lambda: show_memberships(role, for_user=False)).props("flat no-caps")
                    ui.button("History", icon="history", on_click=lambda: show_entity_history("roles", role)).props("flat no-caps")
                    ui.button("Activate" if role["status"] == "inactive" else "Deactivate", icon="toggle_on" if role["status"] == "inactive" else "toggle_off", on_click=change_status).props("outline no-caps")
                    ui.button(
                        "Delete", icon="delete_outline", color="negative",
                        on_click=lambda: confirm_identity_deletion(
                            "roles", role, label="role", on_deleted=lambda: select_entity("roles"),
                        ),
                    ).props("flat no-caps")
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for label, value in (
                        ("Direct status", role.get("status")), ("Effective status", role.get("effective_status")),
                        ("Security clearance", " — ".join(filter(None, (
                            role.get("security_level_code"), role.get("security_level_name"),
                        )))),
                        ("Assigned profile", " — ".join(filter(None, (
                            role.get("profile_code"), role.get("profile_name"),
                        )))),
                        ("Information governance", "Yes" if role.get("is_information_governance") else "No"),
                        ("Organization unit", role.get("org_unit_name")),
                        ("Supervising role", role.get("supervisor_role_name")),
                        ("Supervised roles", role.get("subordinate_role_count")),
                        ("All assignments", role.get("assigned_user_count")),
                        ("Current assignments", role.get("current_assignment_count")),
                        ("Future assignments", role.get("future_assignment_count")),
                        ("Expired assignments", role.get("expired_assignment_count")),
                    ):
                        guidance_text = {
                            "Direct status": "Set directly on this role, without considering its organization structure.",
                            "Effective status": "Also includes inactivity inherited from its organization unit or any ancestor unit.",
                            "Assigned profile": (
                                "All privileges is a migration compatibility profile. Replace it with a purpose-specific profile "
                                "when this role's duties have been reviewed."
                                if role.get("profile_code") == "ALL_PRIVS" else
                                "The role receives its global capabilities from exactly this one profile."
                            ),
                            "Information governance": (
                                "This role may bypass resource ACLs only. Global privileges, its own security clearance, "
                                "effective assignment, closure rules, and other integrity controls still apply."
                            ),
                        }.get(label)
                        with ui.column().classes("gap-0 border-b border-slate-100 pb-1.5"):
                            ui.label(label.upper()).classes("text-xs text-slate-400")
                            ui.label(str(value).title() if value is not None else "—").classes("font-medium")
                            if guidance_text:
                                ui.label(guidance_text).classes("w-full text-[10px] leading-3 text-slate-400")

    async def select_user_details(user_id: int) -> None:
        """Render the extensible single-user management view."""
        register_navigation("user-details", f"User #{user_id}", entity_id=user_id)
        show_authenticated_view()
        state.update(resource="user-details", rows=[], searched=True, aggregation_detail=None)
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        try:
            session_page_size = user_details_session_limit()
            person, assignments = await asyncio.gather(
                api.get("users", user_id), api.user_roles(user_id),
            )
            roles = await api.list("roles")
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        title.text = person["name"]
        subtitle.text = "User details and account administration"
        register_navigation(
            "user-details", person["name"], entity_id=user_id,
            accessible_label=" — ".join(filter(None, (person["name"], person.get("email")))),
        )
        role_by_id = {item["id"]: item for item in roles}

        async def refresh_user(_: Any = None) -> None:
            await select_user_details(user_id)

        async def change_status(action: str) -> None:
            try:
                if action in {"suspend", "unsuspend"}:
                    await api.set_user_suspended(
                        user_id, person["version"], suspended=action == "suspend",
                    )
                else:
                    await api.set_active(
                        "users", user_id, person["version"], active=action == "activate",
                    )
                ui.notify(f"User {action}d", color="positive")
                await refresh_user()
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def issue_password() -> None:
            try:
                result = await api.issue_temporary_password(user_id)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
                return
            dialog = ui.dialog().props("persistent")
            with dialog, ui.card().classes("w-[520px] max-w-full"):
                ui.label("Temporary password issued").classes("text-xl font-semibold")
                ui.label(result["temporary_password"]).classes(
                    "font-mono text-lg bg-slate-100 rounded p-3 select-all"
                )
                ui.label("Copy it now; it will not be shown again.").classes("text-sm text-slate-500")
                ui.button("I have copied it", on_click=dialog.close).props("unelevated no-caps").classes("self-end")
            dialog.open()

        with table_container:
            with ui.column().classes("w-full p-5 gap-4"):
                with ui.card().classes("w-full shadow-none border border-slate-200 p-5"):
                    with ui.row().classes("w-full items-start gap-4"):
                        render_user_avatar(person, size="64px")
                        with ui.column().classes("gap-1 grow"):
                            ui.label(person["name"]).classes("text-xl font-semibold")
                            ui.label(person.get("email") or "No email address").classes("text-slate-500")
                            with ui.row().classes("gap-2"):
                                ui.badge(person["account_type"].title(), color="blue-grey").props("outline")
                                ui.badge(person["status"].title(), color={"active": "positive", "suspended": "warning"}.get(person["status"], "grey-7"))
                        with ui.row().classes("gap-1"):
                            ui.button(
                                "Back", icon="arrow_back",
                                on_click=lambda: breadcrumb_back(lambda: select_entity("users")),
                            ).props("flat no-caps")
                            ui.button("Edit", icon="edit", on_click=lambda: open_editor(person, on_saved=refresh_user, resource_key="users")).props("flat no-caps")
                            ui.button("Role assignments", icon="group", on_click=lambda: show_memberships(person, for_user=True)).props("flat no-caps")
                            ui.button("Temporary password", icon="password", on_click=issue_password).props("flat no-caps color=orange")
                            ui.button("History", icon="history", on_click=lambda: show_entity_history("users", person)).props("flat no-caps")
                            ui.button(
                                "Delete", icon="delete_outline", color="negative",
                                on_click=lambda: confirm_identity_deletion(
                                    "users", person, label="user", on_deleted=lambda: select_entity("users"),
                                ),
                            ).props("flat no-caps")
                    with ui.row().classes("w-full justify-end gap-2"):
                        if person["status"] == "inactive":
                            ui.button("Activate", icon="toggle_on", on_click=lambda: change_status("activate")).props("outline no-caps color=positive")
                        else:
                            ui.button("Deactivate", icon="toggle_off", on_click=lambda: change_status("deactivate")).props("outline no-caps color=negative")
                        if person["status"] == "suspended":
                            ui.button("Unsuspend", icon="play_circle", on_click=lambda: change_status("unsuspend")).props("outline no-caps color=positive")
                        else:
                            suspend = ui.button("Suspend", icon="pause_circle", on_click=lambda: change_status("suspend")).props("outline no-caps color=warning")
                            if person["status"] != "active":
                                suspend.disable(); suspend.tooltip("Activate the user before suspending")
                ui.label("Role assignments").classes("text-lg font-semibold")
                if not assignments:
                    ui.label("No role assignments").classes("text-slate-400")
                else:
                    now = datetime.now(timezone.utc)
                    assignment_rows = []
                    for item in assignments:
                        role = role_by_id.get(item["role_id"], {})
                        valid_from = datetime.fromisoformat(str(item["valid_from"]).replace("Z", "+00:00"))
                        valid_until = datetime.fromisoformat(str(item["valid_until"]).replace("Z", "+00:00")) if item.get("valid_until") else None
                        validity = "future" if valid_from > now else "expired" if valid_until and valid_until <= now else "current"
                        assignment_rows.append({
                            **item, "role": " — ".join(filter(None, (role.get("code"), role.get("name")))) or str(item["role_id"]),
                            "role_status": role.get("effective_status", role.get("status", "unknown")),
                            "validity": validity,
                        })
                    with ui.row().classes("w-full items-end gap-2"):
                        assignment_search = ui.input("Filter role name or code").props("outlined dense clearable").classes("grow")
                        assignment_status = ui.select({"all": "All role statuses", "active": "Active", "inactive": "Inactive"}, value="all", label="Role status").props("outlined dense options-dense").classes("w-44")
                        assignment_validity = ui.select({"all": "All validity", "current": "Current", "future": "Future", "expired": "Expired"}, value="all", label="Assignment validity").props("outlined dense options-dense").classes("w-48")
                    assignment_table = ui.table(columns=[
                        {"name": "role", "label": "Role", "field": "role", "align": "left", "sortable": True},
                        {"name": "role_status", "label": "Role status", "field": "role_status", "align": "left", "sortable": True},
                        {"name": "validity", "label": "Validity", "field": "validity", "align": "left", "sortable": True},
                        {"name": "valid_from", "label": "Valid from", "field": "valid_from", "align": "left", "sortable": True},
                        {"name": "valid_until", "label": "Valid until", "field": "valid_until", "align": "left", "sortable": True},
                    ], rows=assignment_rows, row_key="id", pagination={"rowsPerPage": 5, "sortBy": "role", "descending": False}).props("flat bordered dense").classes("w-full h-[190px] overflow-y-auto")
                    add_timestamp_slots(assignment_table, ["valid_from", "valid_until"])
                    def filter_assignments() -> None:
                        query = (assignment_search.value or "").strip().casefold()
                        assignment_table.rows = [row for row in assignment_rows if (
                            (not query or query in row["role"].casefold())
                            and (assignment_status.value == "all" or row["role_status"] == assignment_status.value)
                            and (assignment_validity.value == "all" or row["validity"] == assignment_validity.value)
                        )]
                        assignment_table.update()
                    for control in (assignment_search, assignment_status, assignment_validity):
                        control.on_value_change(filter_assignments)

                ui.label("Login sessions").classes("text-lg font-semibold")
                session_state = {"offset": 0, "total": 0}
                with ui.row().classes("w-full items-end gap-2"):
                    session_query = ui.input("Filter IP address or client").props("outlined dense clearable").classes("grow")
                    session_status = ui.select({"all": "All statuses", "active": "Active", "expired": "Expired", "revoked": "Revoked"}, value="all", label="Status").props("outlined dense options-dense").classes("w-40")
                    session_sort = ui.select({"date_created": "Signed in", "last_seen_at": "Last activity", "expires_at": "Expiry", "status": "Status", "client_ip": "IP address"}, value="date_created", label="Sort by").props("outlined dense options-dense").classes("w-40")
                    session_direction = ui.select({True: "Newest/descending", False: "Oldest/ascending"}, value=True, label="Direction").props("outlined dense options-dense").classes("w-48")
                session_table = ui.table(columns=[
                    {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
                    {"name": "date_created", "label": "Signed in", "field": "date_created", "align": "left", "sortable": True},
                    {"name": "last_seen_at", "label": "Last activity", "field": "last_seen_at", "align": "left", "sortable": True},
                    {"name": "expires_at", "label": "Expires", "field": "expires_at", "align": "left", "sortable": True},
                    {"name": "client_ip", "label": "IP address", "field": "client_ip", "align": "left", "sortable": True},
                    {"name": "user_agent", "label": "Client", "field": "user_agent", "align": "left"},
                    {"name": "actions", "label": "", "field": "actions", "align": "right"},
                ], rows=[], row_key="id").props("flat bordered dense hide-bottom").classes("w-full h-[190px] overflow-y-auto")
                add_timestamp_slots(session_table, ["date_created", "last_seen_at", "expires_at"])
                session_table.add_slot("body-cell-actions", '''<q-td :props="props"><q-btn v-if="props.row.status === 'active'" flat round dense color="negative" icon="logout" @click="$parent.$emit('revoke', props.row)"><q-tooltip>Force logout this session</q-tooltip></q-btn></q-td>''')
                with ui.row().classes("w-full items-center justify-end gap-2"):
                    session_page_label = ui.label().classes("text-sm text-slate-500")
                    session_previous = ui.button("Previous", icon="chevron_left").props("flat dense no-caps")
                    session_next = ui.button("Next", icon="chevron_right").props("flat dense no-caps")

                async def load_session_page(*, reset: bool = False) -> None:
                    if reset: session_state["offset"] = 0
                    try:
                        page = await api.login_sessions_page(
                            user_id, limit=session_page_size, offset=session_state["offset"],
                            query=session_query.value or "", session_status=session_status.value or "all",
                            sort_by=session_sort.value or "date_created", descending=bool(session_direction.value),
                        )
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True); return
                    session_state["total"] = page["total"]
                    session_table.rows = page["items"]; session_table.update()
                    start = session_state["offset"] + 1 if page["total"] else 0
                    end = min(session_state["offset"] + len(page["items"]), page["total"])
                    session_page_label.text = f"{start}-{end} of {page['total']}"; session_page_label.update()
                    (session_previous.enable if session_state["offset"] > 0 else session_previous.disable)()
                    (session_next.enable if session_state["offset"] + session_page_size < page["total"] else session_next.disable)()

                async def previous_sessions() -> None:
                    session_state["offset"] = max(0, session_state["offset"] - session_page_size); await load_session_page()
                async def next_sessions() -> None:
                    session_state["offset"] += session_page_size; await load_session_page()
                session_previous.on("click", previous_sessions); session_next.on("click", next_sessions)
                for control in (session_query, session_status, session_sort, session_direction):
                    control.on_value_change(lambda: load_session_page(reset=True))
                async def revoke_user_session(event: Any) -> None:
                    try:
                        await api.revoke_session(event.args["id"]); ui.notify("Login session revoked", color="positive"); await load_session_page()
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)
                session_table.on("revoke", revoke_user_session)
                await load_session_page()

    async def show_organization_structure(
        *, selection_mode: str | None = None, target_control: Any = None,
    ) -> None:
        """Shared lazy organization browser for the page and selectors."""
        is_selector = selection_mode is not None
        if not is_selector:
            register_navigation("organization-browser", "Browse organization structure")
        if is_selector:
            dialog = ui.dialog()
            host = dialog
            saved_state: dict[str, Any] = {
                "expanded": [], "selected": None, "query": "", "validity": "all",
                "entity_type": selection_mode or "all", "status": "all", "scroll_top": 0,
            }
        else:
            show_authenticated_view()
            state.update(resource="organization-browser", rows=[], searched=True, aggregation_detail=None)
            title.text = "Browse organization structure"
            subtitle.text = "Explore organization units, roles, and assigned users"
            search_bar.set_visibility(False); aggregation_mode_bar.set_visibility(False)
            add_button.set_visibility(False); add_record_button.set_visibility(False)
            guidance.text = ""; table_container.clear()
            host = table_container
            saved_state = dict(app.storage.user.get("organization_browser_state") or {})
            saved_state.setdefault("expanded", []); saved_state.setdefault("selected", None)
            saved_state.setdefault("query", ""); saved_state.setdefault("validity", "all")
            saved_state.setdefault("entity_type", "all"); saved_state.setdefault("status", "all")
            saved_state.setdefault("scroll_top", 0)

        expanded = set(saved_state["expanded"])
        browser: dict[str, Any] = {"roots": [], "children": {}, "selected": saved_state["selected"]}
        tree_host: Any = None
        summary_host: Any = None
        search_results_host: Any = None
        selection_confirm_button: Any = None

        def persist() -> None:
            if is_selector:
                return
            app.storage.user["organization_browser_state"] = {
                "expanded": sorted(expanded), "selected": browser["selected"],
                "query": query_input.value or "", "validity": validity_filter.value,
                "entity_type": entity_type_filter.value, "status": status_filter.value,
                "scroll_top": browser.get("scroll_top", 0),
            }

        def selection_label(node: dict[str, Any]) -> str:
            if node["type"] in {"role", "org_unit"} and node.get("code"):
                return f"{node['code']} · {node.get('name') or node['id']}"
            return str(node.get("name") or node.get("email") or node["id"])

        def organization_node_dom_id(node: dict[str, Any]) -> str:
            assignment = f"-{node['assignment_id']}" if node.get("assignment_id") else ""
            return f"organization-browser-node-{node['type']}-{node['id']}{assignment}"

        async def select_node(node: dict[str, Any]) -> None:
            browser["selected"] = {
                "type": node["type"], "id": node["id"],
                "selectable": node_selectable(node),
                "label": selection_label(node),
                **({"assignment_id": node.get("assignment_id"), "role_id": node.get("role_id")} if node["type"] == "user" else {}),
            }
            persist()
            await page_client.run_javascript(
                "document.querySelectorAll('#organization-browser-tree .organization-browser-selected')"
                ".forEach(item => item.classList.remove('organization-browser-selected', 'bg-blue-50')); "
                f"document.getElementById('{organization_node_dom_id(node)}')"
                "?.classList.add('organization-browser-selected', 'bg-blue-50');"
            )
            await render_summary(node)
            if is_selector and selection_confirm_button is not None:
                if node_selectable(node):
                    selection_confirm_button.enable()
                else:
                    selection_confirm_button.disable()

        async def load_node_children(node: dict[str, Any]) -> list[dict[str, Any]]:
            key = f"{node['type']}:{node['id']}"
            if key in browser["children"]:
                return browser["children"][key]
            if node["type"] == "org_unit":
                result = await api.organization_children(
                    node["id"], include_roles=selection_mode != "org_unit",
                )
                children = [{**item, "type": "org_unit"} for item in result["org_units"]]
                if selection_mode != "org_unit":
                    children += [{**item, "type": "role"} for item in result["roles"]]
            else:
                children = [] if selection_mode == "role" else [
                    {**item, "type": "user"} for item in await api.organization_role_users(
                        node["id"], validity=validity_filter.value,
                    )
                ]
            browser["children"][key] = children
            return children

        async def toggle_node(node: dict[str, Any]) -> None:
            key = f"{node['type']}:{node['id']}"
            if key in expanded:
                expanded.remove(key)
            else:
                expanded.add(key)
                if key not in browser["children"]:
                    await load_node_children(node)
            persist(); render_tree()

        def node_selectable(node: dict[str, Any]) -> bool:
            if not is_selector or node["type"] != selection_mode:
                return not is_selector
            status = node.get("effective_status", node.get("status"))
            return status == "active"

        def render_nodes(nodes: list[dict[str, Any]], depth: int = 0) -> None:
            for node in nodes:
                key = f"{node['type']}:{node['id']}"
                can_expand = node["type"] == "org_unit" or (
                    node["type"] == "role" and selection_mode not in {"org_unit", "role"}
                )
                selected = (
                    browser["selected"]
                    and browser["selected"].get("type") == node["type"]
                    and browser["selected"].get("id") == node["id"]
                    and (
                        node["type"] != "user"
                        or browser["selected"].get("assignment_id") == node.get("assignment_id")
                    )
                )
                tree_row = ui.row().props(
                    f"id={organization_node_dom_id(node)}"
                ).classes(
                    "w-full items-center no-wrap rounded-lg py-1 pr-2 hover:bg-blue-50 "
                    + ("organization-browser-selected bg-blue-50" if selected else "")
                ).style(f"padding-left:{depth * 20 + 4}px")
                with tree_row:
                    with ui.element("div").classes("w-8 h-8 shrink-0 flex items-center justify-center"):
                        if can_expand:
                            ui.button(
                                icon="expand_more" if key in expanded else "chevron_right",
                                on_click=lambda _, item=node: toggle_node(item),
                            ).props("flat round dense size=sm color=blue-grey")
                    ui.icon(
                        {"org_unit": "corporate_fare", "role": "badge", "user": "person"}[node["type"]],
                        color="primary", size="20px",
                    ).classes("w-6 shrink-0 mr-2")
                    node_content = ui.column().classes(
                        "grow min-w-0 gap-0 py-1 " + ("cursor-pointer" if node_selectable(node) else "")
                    )
                    if node_selectable(node):
                        node_content.on("click", lambda _, item=node: select_node(item))
                        if is_selector:
                            tree_row.on(
                                "dblclick", lambda _, item=node: confirm_node_selection(item),
                            )
                    with node_content:
                        ui.label(node.get("name") or str(node["id"])).classes("text-sm font-semibold line-clamp-1")
                        if node.get("code"):
                            ui.label(node["code"]).classes("text-xs text-slate-400")
                    status_value = node.get("effective_status", node.get("status"))
                    if node["type"] == "user":
                        ui.badge(
                            str(node.get("status") or "active").title(),
                            color={"active": "positive", "suspended": "warning"}.get(node.get("status"), "grey-7"),
                        ).props("outline")
                    elif status_value and status_value != "active":
                        ui.badge(status_value.title(), color="grey-7").props("outline")
                    if is_selector and not node_selectable(node):
                        node_content.tooltip(
                            "This item is visible for context but cannot be selected because it is not active"
                            if node["type"] == selection_mode else "Use this item to navigate the hierarchy"
                        )
                if key in expanded:
                    render_nodes(browser["children"].get(key, []), depth + 1)

        def render_tree() -> None:
            tree_host.clear()
            with tree_host:
                if not browser["roots"]:
                    ui.label("No organization units found").classes("p-4 text-slate-400")
                render_nodes(browser["roots"])

        async def reveal_result(result: dict[str, Any]) -> None:
            """Load and expand the exact ancestor path returned by search."""
            nodes = browser["roots"]
            target: dict[str, Any] | None = None
            for unit_id in result.get("org_unit_path") or []:
                target = next((item for item in nodes if item["id"] == unit_id), None)
                if target is None:
                    return
                key = f"org_unit:{unit_id}"
                expanded.add(key)
                nodes = await load_node_children(target)
            if result["type"] == "role":
                target = next((item for item in nodes if item["type"] == "role" and item["id"] == result["id"]), result)
            elif result["type"] == "user":
                role = next((item for item in nodes if item["type"] == "role" and item["id"] == result.get("role_id")), None)
                if role is not None:
                    expanded.add(f"role:{role['id']}")
                    users = await load_node_children(role)
                    target = next((item for item in users if item.get("assignment_id") == result.get("assignment_id")), result)
                else:
                    target = result
            if target is None:
                target = result
            render_tree()
            await select_node({**target, "type": result["type"]})
            await ui.run_javascript(
                "document.querySelector('#organization-browser-tree .bg-blue-50')?.scrollIntoView({block:'center'})"
            )

        async def open_selected(node: dict[str, Any]) -> None:
            persist()
            if is_selector and not node_selectable(node):
                ui.notify("Select an active item of the requested type", color="warning")
                return
            if node["type"] == "user":
                if is_selector:
                    target_control.set_value(node["id"]); dialog.close()
                else:
                    await select_user_details(node["id"])
            elif is_selector:
                target_control.set_value(node["id"]); dialog.close()
            else:
                if node["type"] == "org_unit":
                    await select_organization_unit_details(node["id"])
                else:
                    await select_role_details(node["id"])

        async def confirm_browser_selection() -> None:
            selected = browser.get("selected")
            if (
                not selected
                or selected.get("type") != selection_mode
                or not selected.get("selectable")
            ):
                ui.notify(
                    f"Select an active {selection_mode.replace('_', ' ')} first",
                    color="warning",
                )
                return
            apply_relationship_selection(
                target_control, selected["id"], selected["label"],
            )
            await asyncio.sleep(0)
            dialog.close()

        async def confirm_node_selection(node: dict[str, Any]) -> None:
            await select_node(node)
            await confirm_browser_selection()

        async def render_summary(node: dict[str, Any]) -> None:
            summary_host.clear()
            if node["type"] in {"org_unit", "role"}:
                item = await api.organization_summary(
                    "org-units" if node["type"] == "org_unit" else "roles", node["id"],
                )
            else:
                item = node
            with summary_host:
                with ui.column().classes("w-full gap-3 p-5"):
                    with ui.row().classes("w-full items-start gap-3 no-wrap"):
                        if node["type"] == "user":
                            render_user_avatar(item, size="38px")
                        else:
                            ui.avatar(
                                icon="corporate_fare" if node["type"] == "org_unit" else "badge",
                                color="blue-1", text_color="primary", size="56px",
                            )
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(item.get("name") or "Selected item").classes("text-xl font-semibold")
                            if item.get("code"): ui.label(item["code"]).classes("text-primary")
                            if item.get("email"): ui.label(item["email"]).classes("text-slate-500")
                    if item.get("description"):
                        ui.label(item["description"]).classes("text-sm text-slate-600 bg-slate-50 rounded p-3 w-full")
                    for label, value in (
                        ("Account status" if node["type"] == "user" else "Effective status", item.get("effective_status", item.get("status"))),
                        ("Account type", item.get("account_type")),
                        ("Organization unit", item.get("org_unit_name")),
                        ("Selected through role", " — ".join(filter(None, (item.get("role_code"), item.get("role_name")))) or None),
                        ("Supervising role", item.get("supervisor_role_name")),
                        ("Direct status", item.get("status") if node["type"] != "user" else None),
                        ("Inactive because of", (item.get("inactive_source") or {}).get("name") if isinstance(item.get("inactive_source"), dict) else None),
                        ("Child units", item.get("child_org_unit_count")),
                        ("Roles", item.get("role_count")),
                        ("Supervised roles", item.get("subordinate_role_count")),
                        ("Assigned users", item.get("assigned_user_count")),
                        ("Current assignments", item.get("current_assignment_count")),
                        ("Future assignments", item.get("future_assignment_count")),
                        ("Expired assignments", item.get("expired_assignment_count")),
                        ("Assignment validity", item.get("assignment_validity")),
                        ("Valid from", format_timestamp(item.get("valid_from")) if item.get("valid_from") else None),
                        ("Valid until", format_timestamp(item.get("valid_until")) if item.get("valid_until") else None),
                    ):
                        if value is not None:
                            guidance_text = None
                            if label == "Effective status":
                                guidance_text = "Includes inactivity inherited from organization-unit ancestors."
                            elif label == "Direct status":
                                guidance_text = "Set directly on this item, without considering its ancestors."
                            with ui.column().classes("w-full gap-0 border-b border-slate-100 py-1.5"):
                                with ui.row().classes("w-full justify-between items-center gap-3"):
                                    ui.label(label).classes("text-xs uppercase tracking-wide text-slate-400")
                                    ui.label(str(value).title() if label in {"Effective status", "Direct status", "Account status", "Account type", "Assignment validity"} else str(value)).classes("text-sm font-medium text-right")
                                if guidance_text:
                                    ui.label(guidance_text).classes("w-full text-[10px] leading-3 text-slate-400")
                    privileges = set(
                        (auth_state.get("principal") or {}).get("global_privileges", [])
                    )
                    if not is_selector and can_open_organization_detail(node["type"], privileges):
                        action_label = f"Open {node['type'].replace('_', ' ')}"
                        ui.button(
                            action_label.title(), icon="open_in_new",
                            on_click=lambda: open_selected(node),
                        ).props("unelevated no-caps").classes("self-end")

        async def run_search() -> None:
            search_results_host.clear()
            query = (query_input.value or "").strip()
            persist()
            if not query:
                return
            type_filter = selection_mode or entity_type_filter.value
            results = await api.search_organization(
                query, entity_type=type_filter, status=status_filter.value,
            )
            with search_results_host:
                if not results:
                    ui.label("No matching organization units, roles, or users").classes("px-2 py-3 text-slate-400")
                for result in results:
                    with ui.card().classes("w-full shadow-none border border-slate-200 p-0"):
                        result_row = ui.row().classes(
                            "w-full items-start gap-3 px-3 py-2 cursor-pointer no-wrap"
                        ).on("click", lambda _, item=result: reveal_result(item))
                        if is_selector:
                            async def confirm_search_result(item: dict[str, Any] = result) -> None:
                                await reveal_result(item)
                                await confirm_browser_selection()
                            result_row.on(
                                "dblclick", lambda _, action=confirm_search_result: action()
                            )
                        with result_row:
                            ui.avatar(
                                icon={"org_unit": "corporate_fare", "role": "badge", "user": "person"}[result["type"]],
                                color="blue-1", text_color="primary", size="36px",
                            ).classes("shrink-0")
                            with ui.column().classes("grow min-w-0 gap-0 items-start text-left"):
                                ui.label(result.get("name") or result.get("code")).classes("font-medium text-left")
                                if result.get("code"):
                                    ui.label(result["code"]).classes("text-xs text-primary text-left")
                                if result.get("email"):
                                    ui.label(result["email"]).classes("text-xs text-slate-500 text-left")
                                if result.get("role_name"):
                                    ui.label(f"Via role: {result.get('role_code')} — {result['role_name']}").classes("text-xs text-slate-500 text-left")

        if is_selector:
            with dialog:
                card_context = ui.card().classes(
                    "w-[1100px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)]"
                )
        else:
            with table_container:
                card_context = ui.column().classes("w-full p-4 gap-3")
        with card_context:
            if is_selector:
                ui.label(f"Browse {selection_mode.replace('_', ' ')}s").classes("text-xl font-semibold")
            with ui.row().classes("w-full items-end gap-2"):
                query_input = ui.input("Search organization structure", value=saved_state.get("query", "")).props("outlined dense clearable").classes("grow")
                validity_filter = ui.select(
                    {"all": "All assignments", "current": "Current", "future": "Future", "expired": "Expired"},
                    value=saved_state.get("validity", "all"), label="Assignment validity",
                ).props("outlined dense options-dense").classes("w-48")
                if selection_mode in {"org_unit", "role"}:
                    validity_filter.set_visibility(False)
                ui.button("Search", icon="search", on_click=run_search).props("flat dense no-caps")
                query_input.on("keydown.enter", run_search)
                filters_button = ui.button("Filters", icon="filter_list").props("flat dense no-caps")
                async def refresh_browser() -> None:
                    browser["children"].clear()
                    try:
                        roots = await api.organization_roots()
                    except ApiError as error:
                        # The shared 401 handler has already cleared protected UI
                        # and opened the sign-in dialog. Do not continue rendering
                        # this page or surface a redundant event-handler traceback.
                        if error.status_code == 401:
                            return
                        raise
                    browser["roots"] = [
                        {**item, "type": "org_unit"} for item in roots
                    ]
                    await restore_expanded(browser["roots"])
                    render_tree()
                    if browser.get("selected"):
                        selected = browser["selected"]
                        try:
                            if selected["type"] == "user" and selected.get("role_id"):
                                candidates = await api.organization_role_users(selected["role_id"], validity="all")
                                refreshed = next((item for item in candidates if item.get("assignment_id") == selected.get("assignment_id")), None)
                                if refreshed: await render_summary({**refreshed, "type": "user"})
                            elif selected["type"] != "user":
                                refreshed = await api.organization_summary("org-units" if selected["type"] == "org_unit" else "roles", selected["id"])
                                await render_summary({**refreshed, "type": selected["type"]})
                        except ApiError:
                            browser["selected"] = None; persist()
                    ui.notify("Organization structure refreshed", color="positive")
                ui.button("Refresh", icon="refresh", on_click=refresh_browser).props("flat dense no-caps")
            with ui.row().classes("w-full items-end gap-2 rounded bg-slate-50 p-2") as advanced_filters:
                entity_type_filter = ui.select(
                    {"all": "All entity types", "org_unit": "Organization units", "role": "Roles", "user": "Users"},
                    value=selection_mode or saved_state.get("entity_type", "all"), label="Entity type",
                ).props("outlined dense options-dense").classes("w-52")
                if is_selector:
                    entity_type_filter.disable()
                status_filter = ui.select(
                    {"all": "All statuses", "active": "Active", "inactive": "Inactive", "suspended": "Suspended"},
                    value=saved_state.get("status", "all"), label="Status",
                ).props("outlined dense options-dense").classes("w-48")
                ui.button("Clear", icon="filter_alt_off", on_click=lambda: (
                    entity_type_filter.set_value(selection_mode or "all"),
                    status_filter.set_value("all"), validity_filter.set_value("all"),
                )).props("flat dense no-caps")
            advanced_filters.set_visibility(False)
            filters_button.on("click", lambda: advanced_filters.set_visibility(not advanced_filters.visible))
            search_results_host = ui.column().classes("w-full gap-0")
            layout_direction = "flex-col" if is_selector else "no-wrap"
            browser_height = "h-[520px]" if is_selector else "h-[720px]"
            with ui.row().classes(f"w-full {browser_height} gap-0 border border-slate-200 rounded-lg overflow-hidden {layout_direction}"):
                tree_classes = (
                    "w-full h-[340px] overflow-auto border-b"
                    if is_selector else "w-1/2 min-w-[360px] h-full overflow-auto border-r"
                )
                tree_host = ui.column().classes(f"{tree_classes} p-2 gap-0 border-slate-200").props("id=organization-browser-tree")
                summary_host = ui.column().classes(
                    "w-full h-[180px] overflow-auto min-w-0"
                    if is_selector else "grow min-w-0 h-full overflow-y-auto"
                )
            if is_selector:
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    selection_confirm_button = ui.button(
                        f"Select {selection_mode.replace('_', ' ')}", icon="check",
                        on_click=confirm_browser_selection,
                    ).props("unelevated no-caps color=primary")
                    selection_confirm_button.disable()
        try:
            roots = await api.organization_roots()
        except ApiError as error:
            # Session expiry and development reloads can race with a navigation
            # click. The API client has already presented sign-in for a 401.
            if error.status_code == 401:
                return
            raise
        browser["roots"] = [{**item, "type": "org_unit"} for item in roots]
        def remember_scroll(event: Any) -> None:
            try:
                browser["scroll_top"] = float(event.args)
                persist()
            except (TypeError, ValueError):
                pass
        tree_host.on("scroll", remember_scroll, js_handler="event => emit(event.target.scrollTop)", throttle=0.25)
        async def change_validity() -> None:
            for key in [key for key in browser["children"] if key.startswith("role:")]:
                browser["children"].pop(key, None)
            persist()
            await restore_expanded(browser["roots"])
            render_tree()
        validity_filter.on_value_change(change_validity)
        async def restore_expanded(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                key = f"{node['type']}:{node['id']}"
                if key in expanded and node["type"] != "user":
                    await restore_expanded(await load_node_children(node))
        await restore_expanded(browser["roots"])
        render_tree()
        if saved_state.get("scroll_top"):
            await ui.run_javascript(
                f"const tree=document.getElementById('organization-browser-tree'); if(tree) tree.scrollTop={float(saved_state['scroll_top'])}"
            )
        if browser["selected"]:
            selected = browser["selected"]
            try:
                if selected["type"] == "user":
                    node = None
                    if selected.get("role_id"):
                        candidates = await api.organization_role_users(
                            selected["role_id"], validity="all",
                        )
                        node = next((item for item in candidates if item.get("assignment_id") == selected.get("assignment_id")), None)
                    if node is None:
                        node = await api.get("users", selected["id"])
                    node["type"] = "user"
                else:
                    node = await api.organization_summary(
                        "org-units" if selected["type"] == "org_unit" else "roles", selected["id"],
                    ); node["type"] = selected["type"]
                await render_summary(node)
            except ApiError:
                browser["selected"] = None; persist()
        else:
            with summary_host:
                guidance_target = (
                    {"org_unit": "organization unit", "role": "role", "user": "user"}[selection_mode]
                    if is_selector else "organization unit, role, or user"
                )
                article = "an" if guidance_target == "organization unit" else "a"
                ui.label(f"Select {article} {guidance_target} to view its summary.").classes("p-8 text-slate-400")
        if is_selector:
            dialog.open()

    async def select_governance_custody() -> None:
        register_navigation("governance-custody", "Governance custody")
        show_authenticated_view()
        state.update(resource="governance-custody", rows=[], searched=True)
        title.text = "Governance custody"
        subtitle.text = "Checks that someone can always manage and recover access to protected records"
        search_bar.set_visibility(False); aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False); add_record_button.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        try:
            report = await api.governance_custody()
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True); return
        highest_level = report.get("highest_security_level")
        warning = next(iter(report.get("warnings", [])), None)
        custodian_count = report["highest_clearance_custodian_count"]
        qualifying_roles = [
            item for item in report["governance_roles"]
            if item["qualifies_for_universal_custody"]
        ]
        qualifying_assignments = [
            item for item in report["assignments"]
            if item["effective_for_universal_custody"]
        ]
        assignments_needing_attention = [
            item for item in report["assignments"]
            if not item["effective_for_universal_custody"]
        ]
        qualifying_roles_by_id = {item["id"]: item for item in qualifying_roles}
        with table_container, ui.column().classes("w-full p-5 gap-4"):
            with ui.element("div").classes("governance-overview-grid"):
                with ui.card().classes("governance-purpose-card shadow-none"):
                    with ui.row().classes("w-full items-start gap-3 no-wrap"):
                        with ui.element("div").classes("governance-purpose-icon"):
                            ui.icon("policy", size="21px")
                        with ui.column().classes("gap-1 grow min-w-0"):
                            ui.label("What this page checks").classes("text-base font-semibold")
                            ui.label(
                                "At least one active person must be able to manage information at the "
                                "highest security level."
                            ).classes("text-sm text-slate-600 leading-relaxed")
                            with ui.element("div").classes("governance-requirements-grid"):
                                for requirement in (
                                    "Governance role enabled",
                                    "Highest clearance held",
                                    "Required profile privileges",
                                    "Current role assignment",
                                ):
                                    with ui.row().classes("items-center gap-2 no-wrap"):
                                        ui.icon("check", color="positive", size="16px")
                                        ui.label(requirement).classes("text-xs text-slate-600")
                            ui.label(
                                "The system blocks relevant changes that would remove the final custodian. "
                                "Keeping at least two is recommended organizational policy."
                            ).classes("text-xs text-slate-500 mt-1")
                critical = bool(warning and warning["severity"] == "critical")
                status_classes = (
                    "governance-status-card governance-status-critical"
                    if critical else
                    "governance-status-card governance-status-warning"
                    if warning else
                    "governance-status-card governance-status-healthy"
                )
                with ui.card().classes(f"{status_classes} shadow-none"):
                    with ui.row().classes("w-full items-start gap-3 no-wrap"):
                        with ui.element("div").classes("governance-status-icon"):
                            ui.icon("priority_high" if warning else "check", size="18px")
                        with ui.column().classes("gap-1 grow min-w-0"):
                            ui.label(
                                "Custody gap detected" if critical else
                                "Custody resilience needs attention" if warning else
                                "Custody coverage is healthy"
                            ).classes("text-base font-semibold")
                            ui.label(
                                "No person currently meets every requirement. Configure a qualifying role "
                                "and assignment."
                                if critical else
                                "Only one person currently qualifies. Add a second custodian to reduce "
                                "operational risk."
                                if warning else
                                f"{custodian_count} active "
                                f"{'person' if custodian_count == 1 else 'people'} currently qualify across "
                                f"{len(qualifying_roles)} governance "
                                f"{'role' if len(qualifying_roles) == 1 else 'roles'} and "
                                f"{len(qualifying_assignments)} current "
                                f"{'assignment' if len(qualifying_assignments) == 1 else 'assignments'}."
                            ).classes("text-sm leading-relaxed")
            with ui.row().classes("governance-metrics-row"):
                for value, label, icon in (
                    (custodian_count, "Universal custodians", "person"),
                    (len(qualifying_roles), "Qualifying roles", "badge"),
                    (len(qualifying_assignments), "Qualifying assignments", "group"),
                ):
                    with ui.card().classes("governance-metric-card shadow-none"):
                        with ui.element("div").classes("governance-metric-icon"):
                            ui.icon(icon, size="18px")
                        with ui.column().classes("gap-0"):
                            ui.label(str(value)).classes("text-2xl font-semibold leading-none")
                            ui.label(label).classes("text-xs text-slate-500 mt-1")
            with ui.row().classes("w-full items-end gap-3 mt-1"):
                with ui.column().classes("gap-0 grow"):
                    ui.label(f"Universal custodians ({custodian_count})").classes(
                        "text-base font-semibold"
                    )
                    ui.label(
                        "Active people whose current assignments provide organization-wide custody "
                        "at the highest configured security level. Each row is a qualifying assignment; "
                        "a person with more than one qualifying role may appear more than once."
                    ).classes("text-xs text-slate-500")
                if highest_level:
                    ui.badge(
                        f"Required clearance: {highest_level['code']} — {highest_level['name']} "
                        f"(level {highest_level['level_number']})"
                    ).props("outline color=primary")
            if qualifying_assignments:
                custodian_rows = [
                    {
                        **item,
                        "person": item["user_name"],
                        "email": item.get("user_email") or "—",
                        "avatar": user_avatar({
                            "id": item["user_id"],
                            "name": item["user_name"],
                            "email": item.get("user_email"),
                        }),
                        "role": f"{item['role_code']} — {item['role_name']}",
                        "clearance": (
                            f"{qualifying_roles_by_id[item['role_id']]['security_level_code']} — "
                            f"{qualifying_roles_by_id[item['role_id']]['security_level_name']}"
                        ),
                        "valid_from_display": format_timestamp(item["valid_from"]),
                        "valid_until_display": (
                            format_timestamp(item["valid_until"]) if item.get("valid_until") else "No expiry"
                        ),
                    }
                    for item in qualifying_assignments
                ]
                custodian_table = ui.table(
                    columns=[
                        {"name": "person", "label": "Person", "field": "person", "sortable": True, "align": "left"},
                        {"name": "email", "label": "Email", "field": "email", "sortable": True, "align": "left"},
                        {"name": "role", "label": "Qualifying role", "field": "role", "sortable": True, "align": "left"},
                        {"name": "clearance", "label": "Clearance", "field": "clearance", "sortable": True, "align": "left"},
                        {"name": "valid_from_display", "label": "Valid from", "field": "valid_from_display", "sortable": True, "align": "left"},
                        {"name": "valid_until_display", "label": "Assignment valid until", "field": "valid_until_display", "sortable": True, "align": "left"},
                        {"name": "actions", "label": "", "field": "actions", "align": "right"},
                    ],
                    rows=custodian_rows,
                    pagination={"rowsPerPage": 5},
                ).props("flat bordered rows-per-page-options='[5,10,25]'").classes(
                    "w-full governance-table"
                )
                custodian_table.add_slot("body-cell-person", """
                    <q-td :props="props">
                      <div class="row items-center no-wrap q-gutter-sm">
                        <q-avatar size="36px"
                          :style="{ backgroundColor: props.row.avatar.color, color: 'white' }">
                          {{ props.row.avatar.initials }}
                        </q-avatar>
                        <span>{{ props.row.person }}</span>
                      </div>
                    </q-td>
                """)
                custodian_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                      <q-btn flat dense no-caps icon="person" color="primary" label="Open user"
                        @click="$parent.$emit('open_user', props.row)" />
                      <q-btn flat dense no-caps icon="badge" color="primary" label="Open role"
                        @click="$parent.$emit('open_role', props.row)" />
                    </q-td>
                """)
                custodian_table.on(
                    "open_user", lambda event: select_user_details(event.args["user_id"])
                )
                custodian_table.on(
                    "open_role", lambda event: select_role_details(event.args["role_id"])
                )
            else:
                ui.label(
                    "No active person currently meets every universal-custody requirement."
                ).classes("governance-empty-inline")
            with ui.row().classes("w-full items-center gap-3"):
                with ui.column().classes("gap-0 grow"):
                    ui.label("Information-governance roles").classes("text-base font-semibold")
                    ui.label(
                        "Qualifying roles provide custody; other listed roles show what is still missing."
                    ).classes("text-xs text-slate-500")
                ui.button(
                    "Open roles", icon="open_in_new", on_click=lambda: select_entity("roles"),
                ).props("flat dense no-caps")
            if not report["governance_roles"]:
                with ui.card().classes("governance-empty-state shadow-none"):
                    ui.icon("verified_user", color="blue-grey-4", size="28px")
                    ui.label("No information-governance roles are configured").classes(
                        "text-sm font-semibold text-slate-700"
                    )
                    ui.label(
                        "Designate the appropriate records-management role, give it the required "
                        "profile and highest clearance, then assign an active person."
                    ).classes("text-xs text-slate-500 text-center")
                    with ui.row().classes("gap-2 mt-1"):
                        ui.button(
                            "Configure a role", icon="badge",
                            on_click=lambda: select_entity("roles"),
                        ).props("outline dense no-caps")
                        ui.button(
                            "Review profiles", icon="admin_panel_settings",
                            on_click=lambda: select_entity("profiles"),
                        ).props("flat dense no-caps")
            else:
                for role in report["governance_roles"]:
                    with ui.card().classes("w-full shadow-none border border-slate-200 p-4 gap-2"):
                        with ui.row().classes("w-full items-center gap-3 no-wrap"):
                            ui.icon("verified_user", color="primary")
                            with ui.column().classes("gap-0 grow min-w-0"):
                                ui.label(f"{role['code']} — {role['name']}").classes("font-semibold")
                                ui.label(
                                    f"Profile: {role['profile_code']} — {role['profile_name']}"
                                ).classes("text-xs text-slate-500")
                            ui.badge(
                                "Qualifies for universal custody"
                                if role["qualifies_for_universal_custody"] else
                                "Does not qualify",
                                color="positive" if role["qualifies_for_universal_custody"] else "warning",
                            ).props("outline")
                            ui.button(
                                "Open role", icon="open_in_new",
                                on_click=lambda _, identifier=role["id"]: select_role_details(identifier),
                            ).props("flat dense no-caps")
                        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                            ui.badge(
                                f"{role['security_level_code']} — {role['security_level_name']} "
                                f"(level {role['level_number']})",
                                color="positive" if role["is_highest_clearance"] else "blue-grey",
                            ).props("outline")
                            ui.badge(
                                "Role and organization active" if role["effective"] else "Role or organization inactive",
                                color="positive" if role["effective"] else "negative",
                            ).props("outline")
                            ui.badge(
                                "All custody privileges present"
                                if role["has_required_custody_privileges"] else
                                f"{len(role['missing_custody_privilege_codes'])} custody privileges missing",
                                color="positive" if role["has_required_custody_privileges"] else "negative",
                            ).props("outline")
                            for count, label, explanation in (
                                (
                                    role["current_assignee_count"], "Current assignments",
                                    "Assignments whose validity dates include the present time.",
                                ),
                                (
                                    role["effective_assignee_count"],
                                    "Active people in an active role",
                                    "Current assignments where the account, role, and organization hierarchy are active.",
                                ),
                                (
                                    role["universal_custodian_count"], "Universal custodians",
                                    "Active person accounts whose qualifying role also has every required privilege and the highest security clearance.",
                                ),
                            ):
                                ui.label(f"{label}: {count}").classes(
                                    "text-xs text-slate-500 cursor-help"
                                ).tooltip(explanation)
                        if role["missing_custody_privilege_codes"]:
                            missing = ", ".join(role["missing_custody_privilege_codes"])
                            ui.label(f"Missing privileges: {missing}").classes(
                                "text-xs font-mono text-red-700 break-all"
                            )

            if assignments_needing_attention:
                with ui.row().classes("w-full items-center gap-3 mt-1"):
                    with ui.column().classes("gap-0 grow"):
                        ui.label("Assignments needing attention").classes("text-base font-semibold")
                        ui.label(
                            "Only assignments that do not currently provide universal custody are listed here."
                        ).classes("text-xs text-slate-500")
                    if highest_level:
                        ui.label(
                            f"Highest configured level: {highest_level['code']} — "
                            f"{highest_level['name']} (level {highest_level['level_number']})"
                        ).classes("text-xs text-slate-500")
                reason_labels = {
                    "service_account": "Service account",
                    "user_inactive": "User inactive",
                    "user_suspended": "User suspended",
                    "assignment_not_current": "Assignment not current",
                    "role_or_organization_inactive": "Role or organization inactive",
                    "role_not_universal_custody_qualified": "Role does not meet universal-custody requirements",
                }
                assignment_rows = []
                for item in assignments_needing_attention:
                    assignment_rows.append({
                        **item,
                        "person": item["user_name"],
                        "role": f"{item['role_code']} — {item['role_name']}",
                        "custody_status": "; ".join(
                            reason_labels.get(reason, reason.replace("_", " ").title())
                            for reason in item["ineffective_reasons"]
                        ),
                    })
                assignment_table = ui.table(
                    columns=[
                        {"name": "person", "label": "Person", "field": "person", "sortable": True, "align": "left"},
                        {"name": "role", "label": "Role", "field": "role", "sortable": True, "align": "left"},
                        {"name": "custody_status", "label": "Custody status", "field": "custody_status", "sortable": True, "align": "left"},
                        {"name": "actions", "label": "", "field": "actions", "align": "right"},
                    ],
                    rows=assignment_rows,
                    pagination={"rowsPerPage": 5},
                ).props("flat bordered rows-per-page-options='[5,10,25]'").classes(
                    "w-full governance-table"
                )
                assignment_table.add_slot("body-cell-actions", """
                    <q-td :props="props">
                      <q-btn flat round dense icon="open_in_new" color="primary"
                        @click="$parent.$emit('open_user', props.row)">
                        <q-tooltip>Open user</q-tooltip>
                      </q-btn>
                    </q-td>
                """)
                assignment_table.on(
                    "open_user", lambda event: select_user_details(event.args["user_id"])
                )

    async def select_security_operations() -> None:
        register_navigation("security-operations", "Security operations")
        show_authenticated_view()
        state.update(resource="security-operations", rows=[], searched=True)
        title.text = "Security operations"; subtitle.text = "Sanitized security signals and access-continuity checks"
        search_bar.set_visibility(False); aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False); add_record_button.set_visibility(False); guidance.text = ""
        table_container.clear()
        privileges = set((auth_state.get("principal") or {}).get("global_privileges", []))
        with table_container, ui.column().classes("w-full p-5 gap-5"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("monitor_heart", color="primary", size="30px")
                with ui.column().classes("gap-0 grow"):
                    window_title = ui.label("Last 24 hours").classes("text-xl font-semibold")
                    ui.label("Aggregated signals contain no protected resource snapshots or request bodies.").classes("text-sm text-slate-500")
                period = ui.select(
                    {"24h": "Last 24 hours", "week": "Last week", "month": "Last month", "custom": "Custom"},
                    value="24h", label="Period",
                ).props("outlined dense options-dense").classes("w-44")
                refresh = ui.button("Refresh", icon="refresh").props("outline no-caps")
            custom_range = ui.row().classes("w-full items-end gap-3")
            with custom_range:
                range_start = ui.input("From").props("outlined dense type=date").classes("w-52")
                range_end = ui.input("Through").props("outlined dense type=date").classes("w-52")
                apply_range = ui.button("Apply range", icon="date_range").props("unelevated no-caps")
            custom_range.set_visibility(False)
            content = ui.column().classes("w-full gap-5")

        def custom_iso(value: str | None, *, end: bool) -> str | None:
            if not value:
                return None
            parsed = datetime.fromisoformat(value).astimezone()
            if end:
                parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
            return parsed.isoformat()

        async def load_security_operations() -> None:
            mode = period.value or "24h"
            hours = {"24h": 24, "week": 24 * 7, "month": 24 * 30}.get(mode, 24)
            if mode == "custom" and (not range_start.value or not range_end.value):
                ui.notify("Select both dates for the custom range", color="warning")
                return
            summary = await api.security_summary(
                hours=hours,
                start_at=custom_iso(range_start.value, end=False) if mode == "custom" else None,
                end_at=custom_iso(range_end.value, end=True) if mode == "custom" else None,
            )
            reconciliation = None
            if "authorization.administer" in privileges:
                reconciliation = await api.security_reconciliation()
            window_title.text = {
                "24h": "Last 24 hours", "week": "Last week", "month": "Last month",
                "custom": f"{range_start.value} through {range_end.value}",
            }[mode]
            content.clear()
            with content:
                full_privilege_roles = summary.get("full_privilege_roles", [])
                if full_privilege_roles:
                    with ui.card().classes(
                        "w-full shadow-none border border-amber-300 bg-amber-50 p-4 gap-3"
                    ):
                        with ui.row().classes("w-full items-start gap-3"):
                            ui.icon("warning_amber", color="amber-9", size="26px").classes(
                                "mt-0.5 shrink-0"
                            )
                            with ui.column().classes("gap-1 grow"):
                                ui.label(
                                    "Roles have profiles containing every system privilege"
                                ).classes("font-semibold text-amber-10")
                                ui.label(
                                    "Each role below is assigned a profile that currently contains "
                                    "every defined privilege. The built-in All privileges profile exists "
                                    "for initial setup and testing, but a custom profile can create the "
                                    "same risk. Before production use, replace these assignments with "
                                    "purpose-specific profiles containing only what each role needs. "
                                    "This is a policy warning; the system does not block the assignment."
                                ).classes("text-sm leading-6 text-amber-10")
                        with ui.column().classes("w-full gap-1 pl-9"):
                            for affected_role in full_privilege_roles:
                                with ui.row().classes("w-full items-center gap-2"):
                                    ui.icon("badge", size="18px").classes("text-amber-9")
                                    ui.label(
                                        f'{affected_role["code"]} — {affected_role["name"]}'
                                    ).classes("grow text-sm font-medium")
                                    ui.badge(
                                        f'{affected_role["profile_code"]} — '
                                        f'{affected_role["profile_name"]}',
                                        color=(
                                            "warning" if affected_role["is_builtin_bootstrap_profile"]
                                            else "amber-8"
                                        ),
                                    ).props("outline")
                                    ui.badge(
                                        affected_role["status"].replace("_", " ").title(),
                                        color="warning",
                                    ).props("outline")
                                    if "organization.administer" in privileges:
                                        ui.button(
                                            "Open role", icon="open_in_new",
                                            on_click=lambda _, role_id=affected_role["id"]: select_role_details(role_id),
                                        ).props("flat dense no-caps color=primary")

                with ui.grid(columns=2).classes("w-full gap-4"):
                    for value, label, icon, help_text in (
                        (summary["total_security_events"], "Security events", "security", "Recognized authentication, authorization, clearance, ACL, profile and governance-policy events in this period."),
                        (summary["total_denials"], "Authorization denials", "gpp_bad", AUTHORIZATION_DENIAL_HELP),
                    ):
                        with ui.card().classes("shadow-none border border-slate-200 p-4 gap-1"):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon(icon, color="primary")
                                ui.label(str(value)).classes("text-3xl font-semibold")
                            ui.label(label).classes("font-medium")
                            ui.label(help_text).classes("text-sm text-slate-500")

                ui.label("Event signals").classes("text-lg font-semibold")
                ui.label("Counts by security operation, with the most recent occurrence in the selected period.").classes("text-sm text-slate-500 -mt-4")
                if not summary["event_counts"]:
                    ui.label("No security events in this period.").classes("text-sm text-slate-400")
                for item in summary["event_counts"]:
                    with ui.grid(columns="minmax(220px, 1fr) minmax(320px, 2fr) 80px 170px").classes("w-full items-center gap-3 border-b border-slate-100 py-3"):
                        ui.label(item["operation"].replace("_", " ").title()).classes("font-medium")
                        ui.label(SECURITY_EVENT_HELP.get(item["operation"], "Security-relevant activity recorded in the audit history.")).classes("text-sm text-slate-500")
                        with ui.row().classes("w-full justify-center"):
                            ui.badge(str(item["count"]), color="primary").props("outline")
                        ui.label(format_timestamp(item["last_seen_at"])).classes("text-xs text-slate-500 text-right")

                ui.label("Recent security events").classes("text-lg font-semibold mt-2")
                ui.label(
                    "The most recent security-related events in the selected period, including "
                    "the account involved, the affected item, and the authorization decision "
                    "when one was recorded. Details you are not authorized to view remain hidden."
                ).classes("text-sm text-slate-500 -mt-4")
                event_rows = [{
                    **item,
                    "actor": item.get("actor_name") or item.get("actor_email") or item.get("actor_type"),
                    "when": format_timestamp(item["occurred_at"]),
                    "signal": item["operation"].replace("_", " ").title(),
                    "decision": decision_code_label(item.get("decision_code")),
                } for item in summary.get("recent_events", [])]
                event_table = ui.table(
                    columns=[
                        {"name": "when", "label": "When", "field": "when", "sortable": True, "align": "left"},
                        {"name": "signal", "label": "Event", "field": "signal", "sortable": True, "align": "left"},
                        {"name": "actor", "label": "Account / actor", "field": "actor", "sortable": True, "align": "left"},
                        {"name": "entity_label", "label": "Target", "field": "entity_label", "sortable": True, "align": "left"},
                        {"name": "decision", "label": "Decision", "field": "decision", "sortable": True, "align": "left"},
                    ], rows=event_rows, pagination={"rowsPerPage": 10}, row_key="id",
                ).props("flat bordered rows-per-page-options='[10,25,50]'").classes(
                    "w-full governance-table security-operations-table"
                )
                event_table.add_slot("body-cell-decision", '''
                    <q-td :props="props">
                      <span>{{ props.value }}</span>
                      <q-tooltip v-if="props.row.decision_code">
                        Technical code: {{ props.row.decision_code }}
                      </q-tooltip>
                    </q-td>
                ''')

                ui.label("Denial monitoring").classes("text-lg font-semibold mt-2")
                ui.label(AUTHORIZATION_DENIAL_HELP).classes("text-sm text-slate-500 -mt-4")
                if not summary["denial_groups"]:
                    ui.label("No authorization denials occurred in this period.").classes("text-sm text-positive")
                for item in summary["denial_groups"]:
                    with ui.card().classes("w-full shadow-none border border-slate-200 p-4 gap-1"):
                        with ui.row().classes("w-full items-center gap-3"):
                            ui.label(item["decision_code"].replace("_", " ").title()).classes("font-medium")
                            ui.label(item["required_privilege"]).classes("grow text-sm text-slate-500")
                            ui.badge(str(item["count"]), color="negative").props("outline")
                        ui.label("Review the recent events above or open the Audit trail to inspect individual events. Details you are not authorized to view remain hidden.").classes("text-sm text-slate-500")

                if reconciliation is not None:
                    ui.separator()
                    ui.label("Administrative access and security-level consistency").classes("text-lg font-semibold")
                    ui.label(
                        "Checks that at least one active person can still manage authorization "
                        "settings, and that no child aggregation or record has a higher security "
                        "level than its parent. Details about governance custodians remain on the "
                        "Governance custody page."
                    ).classes("text-sm text-slate-500 -mt-4")
                    hierarchy_count = reconciliation["hierarchy_violation_count"]
                    with ui.row().classes("w-full items-center gap-3 rounded-lg border p-3 " + ("border-red-200 bg-red-50" if hierarchy_count else "border-green-200 bg-green-50")):
                        ui.icon("warning" if hierarchy_count else "check_circle", color="negative" if hierarchy_count else "positive")
                        ui.label(f"{hierarchy_count} security hierarchy violation{'s' if hierarchy_count != 1 else ''}").classes("font-semibold grow")
                        ui.label("Requires investigation" if hierarchy_count else "No invalid parent-child levels found").classes("text-sm text-slate-600")
                    for finding in reconciliation["findings"]:
                        if "governance_custodian" in finding["code"] or finding["code"] == "security_hierarchy_violation":
                            continue
                        with ui.row().classes("w-full items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3"):
                            ui.icon("warning", color="negative" if finding["severity"] == "critical" else "amber-8")
                            ui.label(finding["code"].replace("_", " ").title()).classes("font-semibold grow")
                            ui.badge(finding["severity"], color="negative" if finding["severity"] == "critical" else "warning")

        def change_period() -> None:
            custom_range.set_visibility(period.value == "custom")
            if period.value != "custom":
                background_tasks.create(load_security_operations())

        period.on_value_change(change_period)
        refresh.on("click", load_security_operations)
        apply_range.on("click", load_security_operations)
        await load_security_operations()

    async def select_entity(key: str) -> None:
        register_navigation(key, ENTITIES[key].label)
        show_authenticated_view()
        state.update(
            resource=key, rows=[], searched=False, aggregation_detail=None,
            lifecycle_filter="all",
        )
        spec = ENTITIES[key]
        title.text = spec.label
        subtitle.text = "Search required before loading results" if spec.search_first else "Manage current system entries"
        aggregation_mode_bar.set_visibility(key == "aggregations")
        search_bar.set_visibility(
            spec.search_first
            and not (key == "aggregations" and state.get("aggregation_mode") == "browse")
        )
        guidance.text = "Large collections are search-first to avoid loading unbounded result sets." if spec.search_first else ""
        add_button.set_visibility(key not in {"privileges", "permissions"})
        add_button.text = "Add"
        add_button.update()
        add_record_button.set_visibility(False)
        search_input.value = ""
        try:
            if key in {"aggregations", "records"}:
                await reload_favourites()
            if spec.search_first:
                await load_recent(spec)
            if key == "aggregations" and state.get("aggregation_mode") == "browse":
                await select_aggregation_browser()
                return
            render_table(spec)
            await load_rows()
        except ApiError as error:
            set_connection_status(error.status_code != 503)
            ui.notify(error_message(error), color="negative", close_button=True)

    async def select_classification_workspace(
        initial_scheme_id: int | None = None,
        initial_classification_id: int | None = None,
    ) -> None:
        register_navigation("classification-workspace", "Classification schemes")
        show_authenticated_view()
        state.update(
            resource="classification-workspace", rows=[], searched=True,
            aggregation_detail=None,
        )
        title.text = "Classification schemes"
        subtitle.text = "Build and govern classification hierarchies in context"
        search_bar.set_visibility(False)
        aggregation_mode_bar.set_visibility(False)
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        guidance.text = ""
        table_container.clear()

        workspace: dict[str, Any] = {
            "schemes": [], "scheme": None, "selected": None,
            "children": {}, "expanded": set(), "counts": {},
            "query": "", "search_results": [],
            "scheme_sort": "created", "scheme_sort_direction": "asc",
            "tree_revision": 0,
        }

        with table_container:
            with ui.column().classes("w-full gap-0"):
                with ui.row().classes(
                    "w-full h-[420px] shrink-0 items-stretch gap-0 no-wrap "
                    "overflow-hidden border-b border-slate-200"
                ):
                    with ui.column().classes(
                        "w-[42%] basis-[42%] shrink-0 min-w-[340px] h-full "
                        "border-r border-slate-200 p-4 gap-3"
                    ):
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.label("Classification schemes").classes("text-lg font-semibold")
                            add_scheme_button = ui.button(
                                "Add scheme", icon="add"
                            ).props("unelevated dense no-caps color=primary").classes("ml-auto")
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            scheme_filter = ui.input("Filter schemes").props(
                                "outlined dense clearable prepend-icon=search"
                            ).classes("grow min-w-0")
                            scheme_sort = ui.select(
                                {
                                    "created": "Creation order",
                                    "title": "Title",
                                    "code": "Code",
                                    "published_status": "Status",
                                },
                                value="created",
                                label="Sort by",
                            ).props("outlined dense options-dense").classes("w-44 shrink-0")
                            scheme_sort_direction = ui.button(
                                icon="arrow_upward"
                            ).props("flat dense round color=primary").classes("shrink-0")
                            scheme_sort_direction.tooltip("Reverse sort direction")
                        scheme_list = ui.column().classes(
                            "w-full grow min-h-0 gap-2 overflow-y-auto pr-1"
                        )
                    scheme_information_panel = ui.column().classes(
                        "grow min-w-0 h-full overflow-y-auto p-5 gap-4"
                    )
                classification_workspace = ui.column().classes(
                    "w-full min-w-0 min-h-[520px] p-5 gap-4"
                )

        def scheme_lifecycle(scheme: dict[str, Any]) -> tuple[str, str]:
            if scheme.get("date_deactivated"):
                return "Inactive", "grey-7"
            published = scheme.get("date_published")
            if not published:
                return "Draft", "blue-grey"
            try:
                publication = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                now = datetime.now(publication.tzinfo or timezone.utc)
                if publication > now:
                    return "Scheduled", "orange"
            except (TypeError, ValueError):
                pass
            return "Published", "positive"

        def scheme_deletion_block_reason(scheme: dict[str, Any]) -> str | None:
            if scheme.get("date_first_used"):
                return (
                    "This scheme cannot be deleted because one or more of its "
                    "classifications have governed an aggregation. Deactivate it instead."
                )
            if scheme.get("date_published"):
                return "Unpublish this unused scheme before deleting it."
            return None

        def metadata_value(
            label: str, value: Any, *, timestamp: bool = False,
        ) -> None:
            with ui.column().classes("gap-0 min-w-0 w-full"):
                ui.label(label.upper()).classes("component-meta-label")
                rendered = format_timestamp(value) if timestamp else display_value(value)
                ui.label(rendered).classes(
                    "w-full text-sm text-slate-700 whitespace-pre-wrap break-words select-text"
                )

        def long_metadata_value(label: str, value: Any) -> None:
            with ui.column().classes("w-full gap-1 min-w-0"):
                ui.label(label.upper()).classes("component-meta-label")
                ui.label(display_value(value)).classes(
                    "w-full min-h-[4.75rem] max-h-32 overflow-y-auto rounded-lg "
                    "border border-slate-200 bg-slate-50 px-3 py-2 text-sm "
                    "leading-6 text-slate-700 whitespace-pre-wrap break-words select-text"
                )

        def render_rule_details(rule: dict[str, Any] | None) -> None:
            if rule is None:
                ui.label("No retention rule is defined here.").classes("text-sm text-slate-400")
                return
            with ui.grid(columns=3).classes("w-full gap-4"):
                metadata_value("Current period", f"{rule['current_period_years']} years")
                metadata_value("Intermediate period", f"{rule['intermediate_period_years']} years")
                metadata_value(
                    "Final disposition",
                    rule["final_disposition"].replace("_", " ").title(),
                )
            metadata_value("Instructions", rule.get("instructions"))

        async def load_scheme_counts(schemes: list[dict[str, Any]]) -> None:
            rows = await api.request(
                "GET", "/api/v1/classification-schemes/classification-counts"
            )
            workspace["counts"] = {
                row["classification_scheme_id"]: (
                    int(row["branch_count"]), int(row["terminal_count"]),
                )
                for row in rows
            }
            for scheme in schemes:
                workspace["counts"].setdefault(scheme["id"], (0, 0))

        def render_scheme_list() -> None:
            scheme_list.clear()
            term = (scheme_filter.value or "").strip().casefold()
            schemes = [
                scheme for scheme in workspace["schemes"]
                if not term or term in " ".join(filter(None, (
                    scheme.get("code"), scheme.get("title"), scheme.get("description"),
                ))).casefold()
            ]
            with scheme_list:
                if not schemes:
                    ui.label("No matching schemes").classes("text-sm text-slate-400 py-5 self-center")
                for scheme in schemes:
                    selected = workspace["scheme"] and workspace["scheme"]["id"] == scheme["id"]
                    status_label, status_color = scheme_lifecycle(scheme)
                    scheme_counts = workspace["counts"].get(scheme["id"])
                    classes = "w-full cursor-pointer shadow-none border p-2"
                    classes += " border-blue-300 bg-blue-50" if selected else " border-slate-200"
                    with ui.card().classes(classes).on(
                        "click", lambda _, item=scheme: select_scheme(item)
                    ):
                        with ui.row().classes("w-full items-start gap-2 no-wrap"):
                            ui.avatar(icon="account_tree", color="blue-1", text_color="primary", size="32px")
                            with ui.column().classes("grow min-w-0 gap-0"):
                                ui.label(scheme["title"]).classes("w-full font-semibold truncate")
                                ui.label(scheme["code"]).classes(
                                    "w-full text-xs font-medium text-primary truncate"
                                )
                                description = scheme.get("description") or "No description"
                                description_label = ui.label(description).classes(
                                    "w-full text-xs text-slate-500 truncate"
                                )
                                if scheme.get("description"):
                                    description_label.tooltip(description)
                            with ui.column().classes(
                                "w-40 shrink-0 items-end gap-1"
                            ):
                                ui.badge(status_label, color=status_color).props("outline")
                                if scheme_counts is None:
                                    ui.label("Counts loading…").classes(
                                        "w-full text-right text-xs text-slate-400 whitespace-nowrap"
                                    )
                                else:
                                    branches, terminals = scheme_counts
                                    ui.label(
                                        f"{branches} {'branch' if branches == 1 else 'branches'} · "
                                        f"{terminals} {'terminal' if terminals == 1 else 'terminals'}"
                                    ).classes("w-full text-right text-xs text-slate-400 whitespace-nowrap")

        async def load_children(parent_id: int | None) -> list[dict[str, Any]]:
            scheme = workspace["scheme"]
            if scheme is None:
                return []
            scheme_id = int(scheme["id"])
            rows = await api.list(
                "classifications",
                classification_scheme_id=scheme_id,
                **({"roots_only": True} if parent_id is None else {"parent_classification_id": parent_id}),
            )
            current_scheme = workspace["scheme"]
            if current_scheme and int(current_scheme["id"]) == scheme_id:
                workspace["children"][parent_id] = rows
            return rows

        async def focus_classification(
            item: dict[str, Any], *, reveal: bool = False,
        ) -> None:
            client = page_client
            if (
                not reveal
                and workspace["selected"]
                and workspace["selected"]["id"] == item["id"]
            ):
                return
            workspace["tree_revision"] += 1
            revision = workspace["tree_revision"]

            def is_current() -> bool:
                return revision == workspace["tree_revision"]

            scroll_top = None
            if not reveal:
                scroll_top = await client.run_javascript(
                    "document.getElementById('classification-tree-scroll')?.scrollTop || 0"
                )
                if not is_current():
                    return
            scheme = next(
                (entry for entry in workspace["schemes"] if entry["id"] == item["classification_scheme_id"]),
                None,
            )
            if scheme is None:
                return
            if workspace["scheme"] is None or workspace["scheme"]["id"] != scheme["id"]:
                workspace.update(scheme=scheme, selected=None, children={}, expanded=set(), query="", search_results=[])
                await load_children(None)
                if not is_current():
                    return
                render_scheme_list()
            path = await api.classification_path(item["id"])
            if not is_current():
                return
            parent_id = None
            for node in path[:-1]:
                if parent_id not in workspace["children"]:
                    await load_children(parent_id)
                    if not is_current():
                        return
                workspace["expanded"].add(node["id"])
                if node["id"] not in workspace["children"]:
                    await load_children(node["id"])
                    if not is_current():
                        return
                parent_id = node["id"]
            workspace["selected"] = item
            await render_workspace_right()
            if reveal:
                await client.run_javascript(
                    "requestAnimationFrame(() => requestAnimationFrame(() => { "
                    "const tree = document.getElementById('classification-tree-scroll'); "
                    f"const node = document.getElementById('classification-tree-node-{item['id']}'); "
                    "if (!tree || !node) return; "
                    "const treeBox = tree.getBoundingClientRect(); "
                    "const nodeBox = node.getBoundingClientRect(); "
                    "if (nodeBox.top < treeBox.top || nodeBox.bottom > treeBox.bottom) "
                    "node.scrollIntoView({block: 'center', behavior: 'smooth'}); "
                    "}));"
                )
            else:
                await client.run_javascript(
                    "requestAnimationFrame(() => requestAnimationFrame(() => { "
                    "const tree = document.getElementById('classification-tree-scroll'); "
                    f"if (tree) tree.scrollTop = {float(scroll_top or 0)}; "
                    "}));"
                )

        async def toggle_branch(item: dict[str, Any]) -> None:
            client = page_client
            workspace["tree_revision"] += 1
            revision = workspace["tree_revision"]
            scroll_top = await client.run_javascript(
                "document.getElementById('classification-tree-scroll')?.scrollTop || 0"
            )
            if revision != workspace["tree_revision"]:
                return
            if item["id"] in workspace["expanded"]:
                workspace["expanded"].remove(item["id"])
            else:
                if item["id"] not in workspace["children"]:
                    await load_children(item["id"])
                    if revision != workspace["tree_revision"]:
                        return
                workspace["expanded"].add(item["id"])
            await render_workspace_right()
            await client.run_javascript(
                "requestAnimationFrame(() => requestAnimationFrame(() => { "
                "const tree = document.getElementById('classification-tree-scroll'); "
                f"if (tree) tree.scrollTop = {float(scroll_top or 0)}; "
                "}));"
            )

        def render_tree_level(
            parent_id: int | None, depth: int = 0, ancestor_inactive: bool = False,
        ) -> None:
            rows = workspace["children"].get(parent_id, [])
            for item in rows:
                directly_inactive = bool(item.get("date_deactivated"))
                effectively_inactive = bool(
                    ancestor_inactive
                    or directly_inactive
                    or (workspace["scheme"] or {}).get("date_deactivated")
                )
                selected = workspace["selected"] and workspace["selected"]["id"] == item["id"]
                tree_row = ui.row().classes(
                    "w-full items-center no-wrap rounded-lg py-1 pr-2 hover:bg-blue-50 "
                    + ("bg-blue-50" if selected else "")
                ).style(f"padding-left: {depth * 20 + 4}px")
                if selected:
                    tree_row.props(f"id=classification-tree-node-{item['id']}")
                with tree_row:
                    with ui.element("div").classes(
                        "w-8 h-8 shrink-0 flex items-center justify-center"
                    ):
                        if not item["is_terminal"]:
                            ui.button(
                                icon="expand_more" if item["id"] in workspace["expanded"] else "chevron_right",
                                on_click=lambda _, node=item: toggle_branch(node),
                            ).props("flat round dense size=sm color=blue-grey")
                    ui.icon(
                        "label" if item["is_terminal"] else "schema",
                        color="primary",
                        size="20px",
                    ).classes("w-6 shrink-0 mr-2")
                    with ui.column().classes("grow min-w-0 gap-0 cursor-pointer py-1").on(
                        "click", lambda _, node=item: focus_classification(node)
                    ):
                        ui.label(item["title"]).classes("text-sm font-semibold line-clamp-1")
                        ui.label(item["code"]).classes("text-xs text-slate-400")
                    if effectively_inactive:
                        inactive_label = "Inactive" if directly_inactive else "Inactive via parent"
                        if (workspace["scheme"] or {}).get("date_deactivated"):
                            inactive_label = "Inactive via scheme"
                        ui.badge(inactive_label, color="grey-7").props("outline")
                    else:
                        ui.badge("Terminal" if item["is_terminal"] else "Branch", color="primary").props("outline")
                if not item["is_terminal"] and item["id"] in workspace["expanded"]:
                    children = workspace["children"].get(item["id"])
                    if children is None:
                        continue
                    if children:
                        render_tree_level(item["id"], depth + 1, effectively_inactive)
                    else:
                        ui.label("No child classifications").classes("text-xs text-slate-400 py-1").style(
                            f"padding-left: {(depth + 1) * 20 + 36}px"
                        )

        async def create_classification(parent: dict[str, Any] | None = None) -> None:
            scheme = workspace["scheme"]
            if scheme is None:
                return
            if parent and parent.get("is_terminal"):
                ui.notify("Terminal classifications cannot contain children", color="warning")
                return

            async def saved(item: dict[str, Any]) -> None:
                await load_children(parent["id"] if parent else None)
                if parent:
                    workspace["expanded"].add(parent["id"])
                await load_scheme_counts(workspace["schemes"])
                render_scheme_list()
                await focus_classification(item, reveal=True)

            await open_editor(
                initial_values={
                    "classification_scheme_id": scheme["id"],
                    "parent_classification_id": parent["id"] if parent else None,
                },
                locked_fields={"classification_scheme_id", "parent_classification_id"},
                on_saved=saved,
                resource_key="classifications",
            )

        async def edit_selected() -> None:
            selected = workspace["selected"]
            if selected is None:
                return

            async def saved(item: dict[str, Any]) -> None:
                parent_id = item.get("parent_classification_id")
                await load_children(parent_id)
                await load_scheme_counts(workspace["schemes"])
                render_scheme_list()
                await focus_classification(item)

            await open_editor(selected, on_saved=saved, resource_key="classifications")

        async def change_classification_lifecycle(item: dict[str, Any]) -> None:
            deactivated = bool(item.get("date_deactivated"))
            action = "reactivate" if deactivated else "deactivate"
            dialog = ui.dialog()
            with dialog, ui.card().classes("w-[540px] max-w-full"):
                ui.label(f"{action.title()} classification?").classes("text-xl font-semibold")
                ui.label(f"{item['code']} — {item['title']}").classes("font-semibold")
                ui.label(
                    "Existing aggregation assignments and retention rules will not be changed. "
                    + (
                        "The classification may still remain unavailable through an inactive ancestor or scheme."
                        if deactivated else
                        "This classification and its descendants will be unavailable for new assignments."
                    )
                ).classes("text-sm text-slate-600")
                reason = ui.textarea(f"Reason for {action}").props("outlined autogrow").classes("w-full")

                async def apply_change() -> None:
                    if not (reason.value or "").strip():
                        ui.notify(f"A reason for {action} is required", color="warning")
                        return
                    try:
                        updated = await api.request(
                            "POST", f"/api/v1/classifications/{item['id']}/{action}",
                            headers={
                                "If-Match": str(item["version"]),
                                "X-Change-Reason": reason.value.strip(),
                            },
                        )
                        dialog.close()
                        ui.notify(f"Classification {action}d", color="positive")
                        await reload_workspace(updated["classification_scheme_id"], updated["id"])
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button(action.title(), on_click=apply_change).props(
                        "unelevated no-caps color=" + ("positive" if deactivated else "negative")
                    )
            dialog.open()

        async def confirm_delete_classification(item: dict[str, Any]) -> None:
            dialog = ui.dialog()
            with dialog, ui.card().classes("w-[540px] max-w-full"):
                ui.label("Delete classification permanently?").classes("text-xl font-semibold")
                ui.label(f"{item['code']} — {item['title']}").classes("font-semibold")
                ui.label(
                    "Its directly owned retention rule and recent-selection references will also be "
                    "removed. Immutable event history will remain. This cannot be undone."
                ).classes("text-sm text-slate-600")
                reason = ui.textarea("Reason for deletion").props("outlined autogrow").classes("w-full")

                async def remove() -> None:
                    if not (reason.value or "").strip():
                        ui.notify("A reason for deletion is required", color="warning")
                        return
                    try:
                        await api.request(
                            "DELETE", f"/api/v1/classifications/{item['id']}",
                            headers={
                                "If-Match": str(item["version"]),
                                "X-Change-Reason": reason.value.strip(),
                            },
                        )
                        dialog.close()
                        ui.notify("Classification deleted", color="positive")
                        await reload_workspace(item["classification_scheme_id"])
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Delete permanently", icon="delete_forever", on_click=remove).props(
                        "unelevated no-caps color=negative"
                    )
            dialog.open()

        async def search_within_scheme(query_control: Any) -> None:
            term = (query_control.value or "").strip()
            workspace["query"] = term
            if not term:
                workspace["search_results"] = []
            else:
                scheme_id = workspace["scheme"]["id"]
                result = await api.search_request("classifications", {
                    "where": {"and": [
                        {"field": "classification_scheme_id", "operator": "eq", "value": scheme_id},
                        {"or": [
                            {"field": field, "operator": "contains_ci", "value": term}
                            for field in CLASSIFICATION_WORKSPACE_SEARCH_FIELDS
                        ]},
                    ]},
                    "sort": [{"field": "code", "direction": "asc"}],
                    "limit": 100,
                })
                workspace["search_results"] = result["items"]
            await render_workspace_right()

        async def render_workspace_right() -> None:
            scheme_information_panel.clear()
            classification_workspace.clear()
            scheme = workspace["scheme"]
            with scheme_information_panel:
                if scheme is None:
                    with ui.column().classes(
                        "w-full h-full items-center justify-center gap-3 text-slate-500"
                    ):
                        ui.icon("account_tree", size="54px").classes("text-primary")
                        ui.label("Select a classification scheme").classes(
                            "text-xl font-semibold text-slate-700"
                        )
                        ui.label("Its information will appear here.").classes("text-sm")
                else:
                    status_label, status_color = scheme_lifecycle(scheme)
                    with ui.row().classes("w-full items-start gap-3"):
                        ui.avatar(icon="account_tree", color="blue-1", text_color="primary")
                        with ui.column().classes("grow min-w-0 gap-0"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label(scheme["title"]).classes("text-xl font-semibold")
                                ui.badge(status_label, color=status_color).props("outline")
                            ui.label(scheme["code"]).classes(
                                "w-full text-sm text-primary font-medium whitespace-normal break-all select-text"
                            )
                    with ui.row().classes("w-full items-center gap-1 flex-wrap"):
                        ui.button("Edit scheme", icon="edit", on_click=lambda: open_editor(
                            scheme, on_saved=lambda _: reload_workspace(scheme["id"]),
                            resource_key="classification-schemes",
                        )).props("flat dense no-caps")
                        ui.button(
                            "Event history", icon="history",
                            on_click=lambda: show_entity_history("classification-schemes", scheme),
                        ).props("flat dense no-caps")
                        if not scheme.get("date_published"):
                            ui.button(
                                "Publish", icon="publish",
                                on_click=lambda: publish_workspace_scheme(scheme),
                            ).props("flat dense no-caps color=primary")
                        else:
                            unpublish_button = ui.button(
                                "Unpublish", icon="unpublished",
                                on_click=lambda: unpublish_workspace_scheme(scheme),
                            ).props("flat dense no-caps color=primary")
                            if scheme.get("date_first_used"):
                                unpublish_button.disable()
                                unpublish_button.tooltip(
                                    "Schemes that have governed aggregations cannot be unpublished"
                                )
                        ui.button(
                            "Reactivate" if scheme.get("date_deactivated") else "Deactivate",
                            icon="toggle_on" if scheme.get("date_deactivated") else "toggle_off",
                            color="positive" if scheme.get("date_deactivated") else "negative",
                            on_click=lambda: change_workspace_scheme_lifecycle(scheme),
                        ).props("flat dense no-caps")
                        deletion_reason = scheme_deletion_block_reason(scheme)
                        branches, terminals = workspace["counts"].get(scheme["id"], (0, 0))
                        delete_label = (
                            "Delete scheme and classifications"
                            if branches + terminals else "Delete scheme"
                        )
                        delete_button = ui.button(
                            delete_label, icon="delete_outline", color="negative",
                            on_click=lambda: confirm_delete_workspace_scheme(scheme),
                        ).props("flat dense no-caps")
                        if deletion_reason:
                            delete_button.disable()
                            delete_button.tooltip(deletion_reason)
                    if deletion_reason:
                        with ui.row().classes(
                            "w-full items-start gap-2 rounded-lg border border-amber-200 "
                            "bg-amber-50 px-3 py-2"
                        ):
                            ui.icon("info", color="amber-8", size="18px").classes("shrink-0 mt-px")
                            ui.label(deletion_reason).classes("text-xs text-amber-900 leading-5")
                    ui.label("Scheme information").classes("font-semibold")
                    with ui.grid(columns=3).classes("w-full gap-4"):
                        metadata_value("Code", scheme.get("code"))
                        metadata_value("Lifecycle", status_label)
                        metadata_value("Edition", scheme.get("edition"))
                        metadata_value("Authority", scheme.get("authority"))
                        metadata_value("Published", scheme.get("date_published"), timestamp=True)
                        metadata_value("First used", scheme.get("date_first_used"), timestamp=True)
                        metadata_value("Deactivated", scheme.get("date_deactivated"), timestamp=True)
                        metadata_value("Created", scheme.get("date_created"), timestamp=True)
                        metadata_value("Last updated", scheme.get("date_updated"), timestamp=True)
                    long_metadata_value("Description", scheme.get("description"))
                    long_metadata_value("Scope note", scheme.get("scope_note"))

            with classification_workspace:
                if scheme is None:
                    with ui.column().classes(
                        "w-full items-center justify-center gap-2 py-16 text-slate-500"
                    ):
                        ui.icon("schema", size="44px").classes("text-primary")
                        ui.label("Select a scheme to browse its classifications.").classes("text-sm")
                    return
                status_label, status_color = scheme_lifecycle(scheme)
                with ui.row().classes("w-full items-end gap-2"):
                    classification_search = ui.input(
                        "Search this scheme", value=workspace["query"],
                    ).props("outlined dense clearable prepend-icon=search").classes("grow")
                    ui.button("Search", icon="search", on_click=lambda: search_within_scheme(classification_search)).props("unelevated dense no-caps")
                    if workspace["query"]:
                        ui.button("Clear", on_click=lambda: clear_classification_search()).props("flat dense no-caps")
                    classification_search.on("keydown.enter", lambda: search_within_scheme(classification_search))

                if workspace["query"]:
                    with ui.card().classes("w-full shadow-none border border-blue-100 bg-blue-50 p-3 gap-2"):
                        ui.label(f"{len(workspace['search_results'])} matching classifications").classes("font-semibold")
                        if not workspace["search_results"]:
                            ui.label("No classifications match this search.").classes("text-sm text-slate-500")
                        for result in workspace["search_results"]:
                            with ui.row().classes("w-full items-center gap-2 cursor-pointer rounded p-2 hover:bg-white").on(
                                "click", lambda _, item=result: focus_classification(item, reveal=True)
                            ):
                                ui.icon("label" if result["is_terminal"] else "schema", color="primary")
                                with ui.column().classes("grow gap-0"):
                                    ui.label(result["title"]).classes("font-semibold")
                                    ui.label(" — ".join(filter(None, (result["code"], result.get("description"))))).classes("text-xs text-slate-500")

                selected = workspace["selected"]
                with ui.grid(columns=2).classes(
                    "w-full h-[620px] min-h-0 gap-4 items-stretch"
                ):
                    with ui.card().classes(
                        "w-full h-full min-h-0 overflow-hidden shadow-none "
                        "border border-slate-200 p-3 gap-1"
                    ):
                        with ui.row().classes("w-full items-center"):
                            ui.label("Classification tree").classes("font-semibold")
                            ui.space()
                            ui.button(
                                icon="add", on_click=lambda: create_classification()
                            ).props("flat round dense color=primary").tooltip(
                                "Add root classification"
                            )
                            child_button = ui.button(
                                icon="subdirectory_arrow_right",
                                on_click=lambda: create_classification(selected)
                                if selected is not None and not selected["is_terminal"]
                                else None,
                            ).props("flat round dense color=primary")
                            if selected is None:
                                child_button.props("disable").tooltip(
                                    "Select a branch classification before adding a child"
                                )
                            elif selected["is_terminal"]:
                                child_button.props("disable").tooltip(
                                    "Terminal classifications cannot contain children"
                                )
                            else:
                                child_button.tooltip(
                                    f"Add child classification beneath {selected['title']}"
                                )
                            ui.button(icon="refresh", on_click=lambda: refresh_tree()).props("flat round dense").tooltip("Refresh tree")
                        with ui.column().classes(
                            "w-full grow min-h-0 overflow-y-auto gap-1 pr-1"
                        ).props("id=classification-tree-scroll"):
                            roots = workspace["children"].get(None, [])
                            if roots:
                                render_tree_level(None)
                            else:
                                ui.label("This scheme has no classifications yet.").classes("text-sm text-slate-400 py-8 self-center")
                    with ui.card().classes(
                        "w-full h-full min-h-0 overflow-y-auto shadow-none "
                        "border border-slate-200 p-4 gap-3"
                    ):
                        if selected is None:
                            ui.label("Select a classification").classes("font-semibold")
                            ui.label("Its metadata and effective retention rule will appear here.").classes("text-sm text-slate-500")
                        else:
                            with ui.row().classes("w-full items-start gap-3"):
                                ui.avatar(icon="label" if selected["is_terminal"] else "schema", color="blue-1", text_color="primary")
                                with ui.column().classes("grow gap-0"):
                                    ui.label(selected["title"]).classes("text-lg font-semibold")
                                    ui.label(selected["code"]).classes(
                                        "w-full text-sm text-primary whitespace-normal break-all select-text"
                                    )
                                ui.badge("Terminal" if selected["is_terminal"] else "Branch", color="primary").props("outline")
                            if selected.get("description"):
                                ui.label(selected["description"]).classes("text-sm text-slate-600")
                            path = await api.classification_path(selected["id"])
                            selected_children = await load_children(selected["id"])
                            inactive_ancestor = next(
                                (item for item in path[:-1] if item.get("date_deactivated")), None,
                            )
                            if scheme.get("date_deactivated"):
                                effective_status = "Inactive via scheme"
                                effective_status_explanation = (
                                    f"The scheme {scheme['code']} — {scheme['title']} is deactivated."
                                )
                            elif selected.get("date_deactivated"):
                                effective_status = "Inactive"
                                effective_status_explanation = (
                                    "This classification is directly deactivated and cannot govern new aggregations."
                                )
                            elif inactive_ancestor:
                                effective_status = "Inactive via ancestor"
                                effective_status_explanation = (
                                    f"Ancestor {inactive_ancestor['code']} — {inactive_ancestor['title']} is deactivated."
                                )
                            else:
                                effective_status = "Active"
                                effective_status_explanation = (
                                    "This classification has no direct or inherited deactivation."
                                )
                            ui.label(" › ".join(item["code"] for item in path)).classes("text-xs text-slate-400")
                            with ui.row().classes("items-center gap-2"):
                                ui.badge(
                                    effective_status,
                                    color="positive" if effective_status == "Active" else "grey-7",
                                ).props("outline")
                                ui.label(effective_status_explanation).classes("text-xs text-slate-500")
                            direct_result, effective_result = await asyncio.gather(
                                api.classification_retention_rule(selected["id"]),
                                api.classification_effective_rule(selected["id"]),
                                return_exceptions=True,
                            )
                            for result in (direct_result, effective_result):
                                if isinstance(result, ApiError) and result.status_code != 404:
                                    raise result
                                if isinstance(result, Exception) and not isinstance(result, ApiError):
                                    raise result
                            direct_rule = direct_result if isinstance(direct_result, dict) else None
                            effective_rule = effective_result if isinstance(effective_result, dict) else None

                            ui.separator()
                            ui.label("Classification information").classes("font-semibold")
                            parent = path[-2] if len(path) > 1 else None
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                metadata_value("Code", selected.get("code"))
                                metadata_value("Authority", selected.get("authority"))
                                metadata_value("Keywords", selected.get("keywords"))
                                metadata_value(
                                    "Parent classification",
                                    f"{parent['code']} — {parent['title']}" if parent else None,
                                )
                                metadata_value("Created", selected.get("date_created"), timestamp=True)
                                metadata_value("Last updated", selected.get("date_updated"), timestamp=True)
                                metadata_value("First used", selected.get("date_first_used"), timestamp=True)
                                metadata_value("Deactivated", selected.get("date_deactivated"), timestamp=True)
                            long_metadata_value("Description", selected.get("description"))
                            long_metadata_value("Scope note", selected.get("scope_note"))

                            ui.separator()
                            ui.label("Effective retention rule").classes("font-semibold")
                            if effective_rule:
                                inherited = effective_rule["defined_by_classification_id"] != selected["id"]
                                source = next(
                                    (
                                        item for item in path
                                        if item["id"] == effective_rule["defined_by_classification_id"]
                                    ),
                                    None,
                                )
                                provenance = "Defined on this classification"
                                if inherited:
                                    provenance = (
                                        f"Inherited from {source['code']} — {source['title']}"
                                        if source else "Inherited from an ancestor classification"
                                    )
                                with ui.row().classes("items-center gap-2"):
                                    ui.badge("Inherited" if inherited else "Direct", color="indigo").props("outline")
                                    ui.label(provenance).classes("text-sm text-slate-500")
                                render_rule_details(effective_rule)
                            else:
                                ui.label("No direct or inherited rule").classes("text-sm text-slate-400")
                            if effective_rule and effective_rule.get("defined_by_classification_id") != selected["id"]:
                                ui.separator()
                                ui.label("Direct retention rule").classes("font-semibold")
                                render_rule_details(direct_rule)
                            with ui.row().classes("w-full justify-end gap-2"):
                                ui.button(
                                    "Event history", icon="history",
                                    on_click=lambda: show_entity_history("classifications", selected),
                                ).props("flat dense no-caps")
                                ui.button("Edit", icon="edit", on_click=edit_selected).props("flat dense no-caps")
                                ui.button(
                                    "Reactivate" if selected.get("date_deactivated") else "Deactivate",
                                    icon="toggle_on" if selected.get("date_deactivated") else "toggle_off",
                                    color="positive" if selected.get("date_deactivated") else "negative",
                                    on_click=lambda: change_classification_lifecycle(selected),
                                ).props("flat dense no-caps")
                                deletion_reason = None
                                if scheme.get("date_deactivated"):
                                    deletion_reason = "Reactivate the scheme before deleting classifications."
                                elif scheme.get("date_published"):
                                    deletion_reason = "Unpublish the scheme before deleting classifications."
                                elif selected.get("date_first_used"):
                                    deletion_reason = (
                                        "This classification has governed an aggregation and can only be deactivated."
                                    )
                                elif selected_children:
                                    deletion_reason = "Remove child classifications first."
                                delete_button = ui.button(
                                    "Delete", icon="delete_outline", color="negative",
                                    on_click=lambda: confirm_delete_classification(selected),
                                ).props("flat dense no-caps")
                                if deletion_reason:
                                    delete_button.disable()
                                    delete_button.tooltip(deletion_reason)
                            if deletion_reason:
                                with ui.row().classes(
                                    "w-full items-start gap-2 rounded-lg border border-amber-200 "
                                    "bg-amber-50 px-3 py-2"
                                ):
                                    ui.icon("info", color="amber-8", size="18px").classes("shrink-0 mt-px")
                                    ui.label(deletion_reason).classes("text-xs text-amber-900 leading-5")

        async def clear_classification_search() -> None:
            workspace["query"], workspace["search_results"] = "", []
            await render_workspace_right()

        async def publish_workspace_scheme(scheme: dict[str, Any]) -> None:
            try:
                await api.request(
                    "POST", f"/api/v1/classification-schemes/{scheme['id']}/publish",
                    headers={"If-Match": str(scheme["version"])},
                )
                ui.notify("Classification scheme published", color="positive")
                await reload_workspace(scheme["id"])
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def unpublish_workspace_scheme(scheme: dict[str, Any]) -> None:
            dialog = ui.dialog()
            with dialog, ui.card().classes("w-[520px] max-w-full"):
                ui.label("Unpublish classification scheme?").classes("text-xl font-semibold")
                ui.label(
                    f"{scheme['code']} — {scheme['title']} will no longer be available "
                    "for new aggregation assignments."
                ).classes("text-sm text-slate-700")
                reason = ui.textarea("Reason for unpublishing").props("outlined autogrow").classes("w-full")

                async def unpublish() -> None:
                    if not (reason.value or "").strip():
                        ui.notify("A reason for unpublishing is required", color="warning")
                        return
                    try:
                        await api.request(
                            "POST", f"/api/v1/classification-schemes/{scheme['id']}/unpublish",
                            headers={
                                "If-Match": str(scheme["version"]),
                                "X-Change-Reason": reason.value.strip(),
                            },
                        )
                        dialog.close()
                        ui.notify("Classification scheme unpublished", color="positive")
                        await reload_workspace(scheme["id"])
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button("Unpublish", icon="unpublished", on_click=unpublish).props(
                        "unelevated no-caps color=primary"
                    )
            dialog.open()

        async def confirm_delete_workspace_scheme(scheme: dict[str, Any]) -> None:
            branches, terminals = workspace["counts"].get(scheme["id"], (0, 0))
            total = branches + terminals
            dialog = ui.dialog()
            with dialog, ui.card().classes("w-[560px] max-w-full"):
                ui.label("Delete classification scheme?").classes("text-xl font-semibold")
                ui.label(f"{scheme['code']} — {scheme['title']}").classes(
                    "font-semibold text-slate-800"
                )
                if total:
                    ui.label(
                        f"This permanently deletes {total} classifications "
                        f"({branches} branches and {terminals} terminals) and their directly "
                        "owned retention rules."
                    ).classes("text-sm text-slate-700")
                else:
                    ui.label("This permanently deletes the empty scheme.").classes(
                        "text-sm text-slate-700"
                    )
                ui.label(
                    "Immutable audit events are retained. This action cannot be undone."
                ).classes("text-xs text-slate-500")
                reason = ui.textarea("Reason for deletion").props("outlined autogrow").classes("w-full")

                async def delete_scheme() -> None:
                    if not (reason.value or "").strip():
                        ui.notify("A reason for deletion is required", color="warning")
                        return
                    try:
                        await api.request(
                            "DELETE", f"/api/v1/classification-schemes/{scheme['id']}",
                            headers={
                                "If-Match": str(scheme["version"]),
                                "X-Change-Reason": reason.value.strip(),
                            },
                        )
                        dialog.close()
                        ui.notify("Classification scheme deleted", color="positive")
                        await reload_workspace()
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
                    ui.button(
                        "Delete permanently", icon="delete_forever", color="negative",
                        on_click=delete_scheme,
                    ).props("unelevated no-caps")
            dialog.open()

        async def change_workspace_scheme_lifecycle(scheme: dict[str, Any]) -> None:
            action = "reactivate" if scheme.get("date_deactivated") else "deactivate"
            try:
                await api.request(
                    "POST", f"/api/v1/classification-schemes/{scheme['id']}/{action}",
                    headers={
                        "If-Match": str(scheme["version"]),
                        "X-Change-Reason": f"{action.title()} from classification administration",
                    },
                )
                ui.notify(f"Classification scheme {action}d", color="positive")
                await reload_workspace(scheme["id"])
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)

        async def refresh_tree() -> None:
            scheme = workspace["scheme"]
            selected = workspace["selected"]
            if scheme is None:
                return
            workspace["tree_revision"] += 1
            revision = workspace["tree_revision"]
            workspace["children"] = {}
            await load_children(None)
            if revision != workspace["tree_revision"]:
                return
            if selected:
                await focus_classification(selected)
            else:
                await render_workspace_right()

        async def select_scheme(scheme: dict[str, Any]) -> None:
            workspace["tree_revision"] += 1
            revision = workspace["tree_revision"]
            workspace.update(
                scheme=scheme, selected=None, children={}, expanded=set(),
                query="", search_results=[],
            )
            await load_children(None)
            if revision != workspace["tree_revision"]:
                return
            render_scheme_list()
            await render_workspace_right()

        async def reload_workspace(
            scheme_id: int | None = None, classification_id: int | None = None,
        ) -> None:
            try:
                schemes = await api.list(
                    "classification-schemes",
                    sort=workspace["scheme_sort"],
                    direction=workspace["scheme_sort_direction"],
                )
                workspace["schemes"] = schemes
                render_scheme_list()
                target_scheme = next((item for item in schemes if item["id"] == scheme_id), None)
                if target_scheme:
                    await select_scheme(target_scheme)
                else:
                    workspace.update(scheme=None, selected=None, children={}, expanded=set())
                    await render_workspace_right()
                if classification_id is not None:
                    try:
                        item = await api.get("classifications", classification_id)
                        await focus_classification(item, reveal=True)
                    except ApiError as error:
                        if error.status_code != 404:
                            raise
                await load_scheme_counts(schemes)
                render_scheme_list()
                set_connection_status(True)
            except ApiError as error:
                set_connection_status(error.status_code != 503)
                ui.notify(error_message(error), color="negative", close_button=True)

        async def create_scheme() -> None:
            async def saved(scheme: dict[str, Any]) -> None:
                await reload_workspace(scheme["id"])
            await open_editor(on_saved=saved, resource_key="classification-schemes")

        scheme_filter.on_value_change(lambda: render_scheme_list())

        async def change_scheme_sort() -> None:
            workspace["scheme_sort"] = scheme_sort.value
            selected_id = workspace["scheme"]["id"] if workspace["scheme"] else None
            await reload_workspace(selected_id)

        async def toggle_scheme_sort_direction() -> None:
            direction = "desc" if workspace["scheme_sort_direction"] == "asc" else "asc"
            workspace["scheme_sort_direction"] = direction
            scheme_sort_direction.props(
                f"icon={'arrow_upward' if direction == 'asc' else 'arrow_downward'}"
            )
            selected_id = workspace["scheme"]["id"] if workspace["scheme"] else None
            await reload_workspace(selected_id)

        scheme_sort.on_value_change(lambda: change_scheme_sort())
        scheme_sort_direction.on("click", toggle_scheme_sort_direction)
        add_scheme_button.on("click", create_scheme)
        await reload_workspace(initial_scheme_id, initial_classification_id)

    for key, button in navigation.items():
        if key == "classification-schemes":
            button.on("click", select_classification_workspace)
        else:
            button.on("click", lambda _, entity_key=key: select_entity(entity_key))
    aggregation_search_mode.on("click", select_aggregation_search)
    aggregation_browse_mode.on("click", select_aggregation_browser)
    dashboard_navigation.on("click", select_dashboard)
    organization_browser_navigation.on("click", show_organization_structure)
    audit_navigation.on("click", select_audit_trail)
    sessions_navigation.on("click", lambda: select_login_sessions())
    security_operations_navigation.on("click", select_security_operations)
    custody_navigation.on("click", select_governance_custody)
    change_password_menu.on("click", show_change_password)
    sign_out_menu.on("click", sign_out)

    async def refresh_user_profile() -> None:
        if auth_state.get("principal"):
            try:
                populate_user_menu(await api.me())
            except ApiError:
                # The shared unauthorized handler presents sign-in when needed.
                pass

    user_menu.on("show", refresh_user_profile)
    async def add_for_current_context() -> None:
        current = state.get("aggregation_detail")
        if not current:
            await open_editor()
            return

        async def refresh_parent(_: dict[str, Any]) -> None:
            await open_aggregation(current)

        await open_editor(
            initial_values={"parent_aggregation_id": current["id"]},
            locked_fields={"parent_aggregation_id"},
            on_saved=refresh_parent, resource_key="aggregations",
        )

    async def add_record_for_current_aggregation() -> None:
        current = state.get("aggregation_detail")
        if current is None:
            return

        async def refresh_parent(_: dict[str, Any]) -> None:
            await open_aggregation(current)

        await open_record_draft_editor(
            target_aggregation_id=current["id"], on_committed=refresh_parent,
        )

    add_button.on("click", add_for_current_context)
    add_record_button.on("click", add_record_for_current_aggregation)
    search_button.on("click", lambda: load_rows())
    search_input.on("keydown.enter", lambda: load_rows())
    login_dialog = ui.dialog().props("persistent")
    with login_dialog:
        ui.element("canvas").classes(
            "wathiq-network-canvas wathiq-login-network"
        ).props(
            "aria-label='Slowly moving connected-node background'"
        )
        with ui.card().classes("wathiq-login-card"):
            with ui.row().classes("w-full items-stretch no-wrap gap-0"):
                with ui.column().classes(
                    "wathiq-login-brand-panel shrink-0 justify-between gap-0"
                ):
                    with ui.column().classes("gap-6"):
                        with ui.row().classes("items-center gap-3 no-wrap"):
                            ui.image("/static/brand/wathiq-mark.svg?v=2").classes(
                                "wathiq-login-mark"
                            ).props("fit=contain alt='Wathiq mark'")
                            ui.label("wathiq").classes("wathiq-login-word")
                        with ui.column().classes("gap-2"):
                            ui.label("Your records.\nYour evidence.\nIn order.").classes(
                                "text-2xl font-semibold leading-tight whitespace-pre-line"
                            )
                            ui.label(
                                "Secure access to the Sharjah Archives records management workspace."
                            ).classes("text-sm leading-5 text-slate-600")
                    ui.label(
                        "Reliable stewardship\nAccountable governance\nTrusted access"
                    ).classes("text-xs leading-5 text-slate-500 whitespace-pre-line")
                with ui.column().classes("wathiq-login-form gap-3"):
                    ui.label("Sign in").classes("text-2xl font-semibold")
                    ui.label("Use your organization credentials to continue.").classes(
                        "text-sm text-slate-500 mb-2"
                    )
                    login_email = ui.input("Email address").props(
                        "outlined autocomplete=username"
                    ).classes("w-full")
                    login_password = ui.input(
                        "Password", password=True, password_toggle_button=True
                    ).props("outlined autocomplete=current-password").classes("w-full")
                    login_error = ui.label().classes(
                        "wathiq-login-error text-negative text-sm"
                    )
                    login_submit = ui.button("Continue to wathiq", icon="login").props(
                        "unelevated no-caps"
                    ).classes("w-full")
                    ui.label("Need help? Contact your system administrator.").classes(
                        "w-full text-center text-xs text-slate-400 mt-1"
                    )

        async def submit_login() -> None:
            login_error.text = ""
            try:
                principal, token = await api.login(
                    login_email.value or "", login_password.value or "",
                    user_agent=context.client.request.headers.get("user-agent"),
                )
                app.storage.user["session_token"] = token
                api.set_session_token(token)
                populate_user_menu(principal)
                navigation_state["trail"] = []
                app.storage.user.pop("navigation_trail", None)
                login_password.value = ""
                login_dialog.close()
                if principal["must_change_password"]:
                    # Until the password is replaced, FastAPI intentionally
                    # rejects every endpoint except /auth/me, change-password,
                    # and logout.  Do not make ordinary application requests
                    # (such as favourites) before showing this dialog.
                    drawer.hide()
                    with table_container:
                        await show_change_password()
                else:
                    await reload_favourites()
                    await select_dashboard()
            except ApiError as error:
                login_error.text = error_message(error)

        login_submit.on("click", submit_login)
        login_password.on("keydown.enter", submit_login)

    def handle_unauthorized() -> None:
        """Synchronize the visible UI when FastAPI rejects a session."""
        api.set_session_token(None)
        try:
            app.storage.user.pop("session_token", None)
        except RuntimeError:
            # Background tasks may not have NiceGUI's storage request context.
            pass
        clear_signed_in_identity()
        set_connection_status(True)  # A 401 proves that the API is reachable.
        login_dialog.open()

    api.set_unauthorized_handler(handle_unauthorized)

    async def initialize_authenticated_ui() -> None:
        # Create a real script node and wait for its load event. NiceGUI inserts
        # add_head_html content dynamically, where ordinary script tags are inert.
        await ui.run_javascript(
            "new Promise((resolve, reject) => {"
            "if (window.startWathiqLoginNetwork) { resolve(true); return; }"
            "const script = document.createElement('script');"
            "script.src = '/static/login/network-background.js?v=5';"
            "script.onload = () => resolve(true);"
            "script.onerror = () => reject(new Error('Login animation failed to load'));"
            "document.head.appendChild(script);"
            "})",
            timeout=15,
        )
        await ui.run_javascript(
            "import('/static/pdfjs/erms-viewer.mjs').then(() => true)", timeout=15,
        )
        token = app.storage.user.get("session_token")
        if token:
            api.set_session_token(token)
            try:
                principal = await api.me()
                populate_user_menu(principal)
                if principal["must_change_password"]:
                    drawer.hide()
                    with table_container:
                        await show_change_password()
                else:
                    await reload_favourites()
                if principal["must_change_password"]:
                    return
                if navigation_state["trail"]:
                    navigation_state["restoring"] = True
                    try:
                        await restore_navigation_entry(navigation_state["trail"][-1])
                    finally:
                        navigation_state["restoring"] = False
                        render_navigation_breadcrumbs()
                else:
                    await select_dashboard()
                return
            except ApiError:
                app.storage.user.pop("session_token", None)
                api.set_session_token(None)
        clear_authenticated_view()
        set_connection_status(True)
        drawer.hide()
        login_dialog.open()
        await ui.run_javascript(
            "window.startWathiqLoginNetwork?.(); true",
            timeout=5,
        )

    ui.timer(0.05, initialize_authenticated_ui, once=True)


def run() -> None:
    ui.run(
        title="wathiq",
        host=host(),
        port=port(),
        reload=reload_enabled(),
        storage_secret=storage_secret(),
        favicon=Path(__file__).with_name("static") / "brand" / "wathiq-mark.svg",
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
