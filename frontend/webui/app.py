from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nicegui import app, background_tasks, context, events, ui

from .api_client import ApiError, ErmsApiClient
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

CLASSIFICATION_WORKSPACE_SEARCH_FIELDS = ("code", "title", "description", "keywords")
CLASSIFICATION_SELECTOR_SEARCH_FIELDS = ("code", "title", "description", "keywords")
CHILD_AGGREGATION_CLASSIFICATION_HELP = (
    "Child aggregations inherit classification governance from their root aggregation "
    "and cannot have a classification assigned directly."
)
RECORD_UPLOAD_WAIT_MESSAGE = "Please wait until all files have finished uploading."
AGGREGATION_SUMMARY_LAYOUT_CLASSES = (
    "bg-blue-50 border border-blue-100 shadow-none flex-1 min-w-[360px]"
)
RECORD_DETAIL_HEADER_CLASSES = "w-full items-start gap-2 no-wrap"
RECORD_DETAIL_TITLE_CLASSES = "gap-0 grow min-w-0"
NAVIGATION_TRAIL_LIMIT = 20
NAVIGATION_VISIBLE_LIMIT = 5
STOP_PROPAGATION_CLICK_HANDLER = "(event) => { event.stopPropagation(); emit(); }"


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
                                "flat round dense" + (" disable" if status != "available" else "")
                            ).tooltip("View document")
                        if on_download is not None:
                            ui.button(icon="download", on_click=lambda _, item=component: on_download(item)).props(
                                "flat round dense" + (" disable" if status != "available" else "")
                            ).tooltip("Download original")
                        ui.button(icon="arrow_upward", on_click=lambda _, item=component: on_move(item, -1)).props(
                            "flat round dense" + (" disable" if readonly or index == 0 else "")
                        ).tooltip("Move earlier")
                        ui.button(icon="arrow_downward", on_click=lambda _, item=component: on_move(item, 1)).props(
                            "flat round dense" + (" disable" if readonly or index == len(rows) - 1 else "")
                        ).tooltip("Move later")
                        ui.button(icon="delete_outline", color="negative", on_click=lambda _, item=component: on_remove(item)).props(
                            "flat round dense" + (" disable" if readonly else "")
                        ).tooltip("Remove component" if not readonly else "Closed records cannot be changed")
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
    if field.kind == "account_type":
        return ui.select(
            {"person": "Person", "service": "Service"},
            label=field.label, value=value or "person",
        ).props("outlined").classes("w-full")
    if field.kind == "classification_type":
        return ui.select(
            {False: "Branch — may contain children", True: "Terminal — assignable to root aggregations"},
            label=field.label, value=False if value is None else value,
        ).props("outlined").classes("w-full")
    if field.kind == "disposition":
        return ui.select({
            "destruction": "Destruction",
            "transfer_to_external_archive": "Permanent preservation — external archive",
            "selective_preservation": "Selective preservation",
            "retain_as_local_archives": "Retain as local archives",
        }, label=field.label, value=value, clearable=True).props("outlined").classes("w-full")
    if field.kind == "textarea":
        return ui.textarea(field.label, value=value or "").props("outlined autogrow").classes("w-full")
    if field.kind == "int":
        return ui.number(field.label, value=value, format="%.0f").props("outlined").classes("w-full")
    if field.kind in {"lookup", "classification"}:
        return relationship_select(
            field.label, options or {}, value=value, required=field.required
        )
    if field.kind == "datetime":
        rendered = str(value or "")[:16]
        return ui.input(field.label, value=rendered).props("outlined type=datetime-local").classes("w-full")
    return ui.input(field.label, value=value or "").props("outlined").classes("w-full")


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

    ui.add_css("""
        :root { --erms-navy: #16324f; --erms-blue: #2563eb; --erms-bg: #f4f7fb; }
        body { background: var(--erms-bg); color: #172033; }
        .erms-header { background: var(--erms-navy); color: white; }
        .erms-drawer { background: #0f2740; color: #dce8f5; }
        .erms-nav-link { border-radius: 8px; }
        .erms-nav-link .q-btn__content {
            width: 100%; gap: 12px; flex-wrap: nowrap; justify-content: flex-start;
        }
        .erms-nav-link .q-btn__content .block {
            min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .erms-nav-link:hover { background: rgba(255, 255, 255, .13) !important; }
        .erms-drawer--collapsed .erms-nav-link .q-btn__content {
            justify-content: center;
        }
        .erms-content { max-width: 1500px; margin: 0 auto; }
        .erms-card { border: 1px solid #e2e8f0; box-shadow: 0 8px 28px rgba(15,39,64,.06); }
        .relationship-select .q-field__control { min-height: 58px; border-radius: 10px; }
        .relationship-option { min-width: 360px; }
        .relationship-option:hover { background: #f3f7ff; }
        .relationship-select .q-field__native { font-weight: 600; color: #16324f; }
        .relationship-cell-name { color: #172033; }
        .recent-card { min-height: 62px; border: 1px solid #e2e8f0; border-radius: 10px; transition: all .16s ease; }
        .recent-card:hover { border-color: #93b4e8; transform: translateY(-2px); box-shadow: 0 8px 22px rgba(37,99,235,.10); }
        .breadcrumb-link { color: #52657a; }
        .timestamp-date { font-size: .84rem; font-weight: 600; color: #334155; line-height: 1.15; }
        .timestamp-time { font-size: .72rem; color: #94a3b8; line-height: 1.2; }
        .component-grid { display: grid; grid-template-columns: 1fr; gap: 12px; padding-right: 8px; }
        .component-list { container-type: inline-size; overflow: visible; padding: 2px 0; }
        @container (min-width: 760px) { .component-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        .component-card { border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: none; overflow: hidden; }
        .component-card:hover { border-color: #a8bdd8; box-shadow: 0 5px 16px rgba(30, 64, 175, .07); }
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
        .dashboard-stat:hover { border-color: #93b4e8; transform: translateY(-2px); box-shadow: 0 8px 22px rgba(37,99,235,.08); }
    """)

    with ui.header(elevated=True).classes("erms-header items-center gap-3"):
        drawer_toggle_button = ui.button(icon="menu").props(
            "flat round color=white aria-label='Collapse navigation'"
        )
        ui.icon("inventory_2").classes("text-2xl")
        ui.label("ERMS").classes("text-xl font-semibold tracking-wide")
        ui.space()
        with ui.icon("cloud_done").classes("text-positive text-xl") as connection_icon:
            connection_tooltip = ui.tooltip("Connected")
        user_menu_button = ui.button(icon="account_circle").props("flat round color=white")
        with user_menu_button, ui.menu() as user_menu:
            with ui.column().classes("w-72 p-3 gap-2"):
                current_user_name = ui.label("Not signed in").classes("font-semibold")
                current_user_email = ui.label().classes("text-xs text-slate-500")
                ui.separator()
                ui.label("Assigned roles").classes("component-meta-label")
                current_user_roles = ui.column().classes("w-full gap-1")
                ui.separator()
                change_password_menu = ui.button("Change password", icon="password").props("flat no-caps align=left").classes("w-full")
                my_sessions_menu = ui.button("Login sessions", icon="devices").props("flat no-caps align=left").classes("w-full")
                sign_out_menu = ui.button("Sign out", icon="logout", color="negative").props("flat no-caps align=left").classes("w-full")

    def set_connection_status(connected: bool) -> None:
        connection_icon.name = "cloud_done" if connected else "cloud_off"
        connection_icon.classes(
            replace="text-positive text-xl" if connected else "text-negative text-xl"
        )
        connection_tooltip.text = "Connected" if connected else "Disconnected"
        connection_icon.update()
        connection_tooltip.update()

    drawer_links: list[tuple[Any, str]] = []
    drawer_headings: list[Any] = []

    def drawer_link(label: str, icon: str, *, extra_classes: str = "") -> Any:
        button = ui.button(label, icon=icon).props(
            f'flat align=left no-caps aria-label="{label}"'
        ).classes(f"erms-nav-link w-full justify-start px-4 {extra_classes}")
        with button:
            ui.tooltip(label)
        drawer_links.append((button, label))
        return button

    with ui.left_drawer(value=True).props(
        "width=300 mini-width=64 show-if-above bordered"
    ).classes("erms-drawer") as drawer:
        navigation: dict[str, Any] = {}
        dashboard_navigation = drawer_link("Dashboard", "dashboard", extra_classes="mt-4")
        for heading, entries in (
            ("RECORDS MANAGEMENT", (("aggregations", "folder"), ("records", "description"), ("classification-schemes", "account_tree"))),
            ("ORGANIZATION STRUCTURE", (("org-units", "corporate_fare"), ("roles", "badge"), ("users", "group"))),
        ):
            drawer_headings.append(
                ui.label(heading).classes("text-xs tracking-widest opacity-60 px-4 pt-5 pb-2")
            )
            if heading == "ORGANIZATION STRUCTURE":
                organization_browser_navigation = drawer_link("Browse", "lan")
            for key, icon in entries:
                navigation[key] = drawer_link(ENTITIES[key].label, icon)
        drawer_headings.append(
            ui.label("SYSTEM ADMINISTRATION").classes(
                "text-xs tracking-widest opacity-60 px-4 pt-5 pb-2"
            )
        )
        audit_navigation = drawer_link("Audit trail", "manage_history")
        sessions_navigation = drawer_link("Login sessions", "devices")

    drawer_collapsed = False

    def toggle_navigation_drawer() -> None:
        nonlocal drawer_collapsed
        drawer_collapsed = not drawer_collapsed
        if drawer_collapsed:
            drawer.props(add="mini")
            drawer.classes(add="erms-drawer--collapsed")
            drawer_toggle_button.props(
                remove="aria-label", add="aria-label='Expand navigation'"
            )
            for heading in drawer_headings:
                heading.set_visibility(False)
            for button, _ in drawer_links:
                button.text = ""
                button.classes(add="justify-center px-0", remove="justify-start px-4")
                button.update()
        else:
            drawer.props(remove="mini")
            drawer.classes(remove="erms-drawer--collapsed")
            drawer_toggle_button.props(
                remove="aria-label", add="aria-label='Collapse navigation'"
            )
            for heading in drawer_headings:
                heading.set_visibility(True)
            for button, label in drawer_links:
                button.text = label
                button.classes(add="justify-start px-4", remove="justify-center px-0")
                button.update()
        drawer.update()
        drawer_toggle_button.update()

    drawer_toggle_button.on("click", toggle_navigation_drawer)

    with ui.column().classes("erms-content w-full p-5 gap-4"):
        breadcrumb_host = ui.element("nav").props(
            "aria-label='Navigation history'"
        ).classes("w-full min-h-7")
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                title = ui.label().classes("text-2xl font-semibold")
                subtitle = ui.label().classes("text-sm text-slate-500")
            ui.space()
            add_button = ui.button("Add", icon="add", color="primary").props("unelevated rounded")
            add_record_button = ui.button(
                "Add record", icon="note_add", color="secondary"
            ).props("unelevated rounded")

        with ui.card().classes("erms-card w-full p-0") as content_card:
            with ui.row().classes("w-full items-center px-4 pt-4 gap-2") as aggregation_mode_bar:
                ui.label("View").classes("text-xs font-semibold uppercase tracking-wide text-slate-400 mr-1")
                aggregation_search_mode = ui.button("Search", icon="search").props(
                    "unelevated dense no-caps color=primary"
                )
                aggregation_browse_mode = ui.button(
                    "Browse classification", icon="account_tree"
                ).props("flat dense no-caps color=primary")
            with ui.row().classes("w-full items-end p-4 gap-2") as search_bar:
                search_input = ui.input("Search by number, title or description").props("outlined clearable").classes("grow")
                search_button = ui.button("Search", icon="search").props("unelevated")
            guidance = ui.label().classes("px-4 pb-4 text-slate-500")
            table_container = ui.column().classes("w-full gap-0")
    content_card.set_visibility(False)
    aggregation_mode_bar.set_visibility(False)
    add_button.set_visibility(False)
    add_record_button.set_visibility(False)

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
        user_menu.close()
        auth_state["principal"] = None
        current_user_name.text = "Not signed in"
        current_user_email.text = ""
        current_user_roles.clear()
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
                        {"field": field.replace("_", " ").title(), "before": event_value(before.get(field)), "after": event_value(after.get(field))}
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
            aggregations = await api.list("aggregations")
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
                else:
                    uploader_control["uploader"] = component_uploader(uploaded)
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
            with ui.card().classes("w-full shadow-none border border-slate-200 p-5 gap-4"):
                with ui.row().classes(f"w-full {RECORD_DETAIL_HEADER_CLASSES} gap-3"):
                    ui.avatar(icon="description", color="blue-1", text_color="primary", size="58px")
                    with ui.column().classes(RECORD_DETAIL_TITLE_CLASSES):
                        ui.label(record["title"]).classes("text-xl font-semibold break-words")
                        ui.label(record["record_number"]).classes("text-sm text-primary font-medium")
                    favourite_button("records", record["id"])
                    ui.button("Back", icon="arrow_back", on_click=leave_record_page).props("flat no-caps")
                    if not record.get("_effectively_closed"):
                        ui.button(
                            "Edit", icon="edit",
                            on_click=lambda: open_editor(
                                record, on_saved=refresh_record_view, resource_key="records",
                            ),
                        ).props("flat no-caps")
                        ui.button(
                            "Delete", icon="delete_outline", color="negative",
                            on_click=confirm_delete_record,
                        ).props("flat no-caps")
                    ui.button(
                        "Event history", icon="history",
                        on_click=lambda: show_entity_history("records", record),
                    ).props("flat no-caps")
                if record.get("_effectively_closed"):
                    with ui.row().classes("w-full items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg"):
                        ui.icon("lock", color="amber-8")
                        ui.label("This record is read-only because its aggregation hierarchy is closed.").classes("text-sm text-amber-900")
                if record.get("description"):
                    ui.label(record["description"]).classes("w-full text-slate-600 whitespace-pre-wrap")
                ui.separator()
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for label, value in (
                        ("Originated", format_timestamp(record.get("date_originated"))),
                        ("Created", format_timestamp(record.get("date_created"))),
                        ("Containing aggregation", record.get("aggregation_display")),
                    ):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(label.upper()).classes("text-xs text-slate-400")
                            if label == "Containing aggregation" and isinstance(value, dict):
                                aggregation_label = " — ".join(filter(None, (value.get("code"), value.get("name"))))
                                ui.button(
                                    aggregation_label,
                                    on_click=open_containing_aggregation,
                                ).props("flat dense no-caps color=primary align=left").classes(
                                    "font-medium self-start -ml-2"
                                )
                            else:
                                ui.label(str(value or "—")).classes("font-medium text-slate-700")

            with ui.card().classes("w-full shadow-none border border-slate-200 p-5 gap-4"):
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
            units = await api.list("org-units")
            by_id = {item["id"]: item for item in units}
            decorated = decorate_relationship_rows(spec.key, rows, units)
            result = []
            for item in decorated:
                source = inactive_org_unit_source(by_id.get(item.get("org_unit_id")), by_id)
                effective = item.get("status") == "active" and source is None
                result.append({
                    **item,
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
            aggregations = await api.list("aggregations")
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
                await api.update_record_draft(draft["id"], payload)
                committed_record = await api.commit_record_draft(draft["id"])
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
                with ui.grid(columns=2).classes("w-full gap-3"):
                    for field in spec.fields:
                        options = relationship_options(aggregations, field.lookup_label_fields) if field.lookup_resource else None
                        controls[field.name] = field_input(field, options=options)
                        if field.name == "aggregation_id" and target_aggregation_id is not None:
                            controls[field.name].value = target_aggregation_id
                            controls[field.name].disable()
                        if field.kind == "textarea":
                            controls[field.name].classes("col-span-2")
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
        if row and spec.key in {"aggregations", "records"} and row.get("_effectively_closed"):
            ui.notify(
                f"Closed {spec.singular} metadata cannot be changed",
                color="warning",
            )
            return
        if creating and spec.key == "records":
            await open_record_draft_editor()
            return
        lookup_options: dict[str, dict[int, str]] = {}
        retention_rule: dict[str, Any] | None = None
        try:
            if row and spec.key == "classifications":
                try:
                    retention_rule = await api.classification_retention_rule(row["id"])
                except ApiError as error:
                    if error.status_code != 404:
                        raise
            for field in spec.fields:
                if not field.lookup_resource:
                    continue
                lookup_rows = await api.list(
                    field.lookup_resource,
                    **({"eligible": True} if field.kind == "classification" else {}),
                )
                if row and field.lookup_resource == spec.key:
                    lookup_rows = [item for item in lookup_rows if item["id"] != row["id"]]
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
            with ui.column().classes("w-full gap-3"):
                for field in spec.fields:
                    source = retention_rule if field.name in {
                        "current_period_years", "intermediate_period_years",
                        "final_disposition", "instructions",
                    } else row
                    controls[field.name] = field_input(
                        field,
                        (initial_values or {}).get(field.name) if creating else source.get(field.name) if source else None,
                        lookup_options.get(field.name),
                    )
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
                    if field.name in (locked_fields or set()):
                        controls[field.name].disable()
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

            async def save() -> None:
                try:
                    payload = form_payload(spec, controls, creating=creating)
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
                        saved = await api.update(spec.key, row["id"], row["version"], payload)
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
            if closure is None:
                add_button.text = "Add child aggregation"
                add_button.update()
                add_button.set_visibility(True)
                add_record_button.set_visibility(True)
            else:
                add_button.set_visibility(False)
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
                        if current.get("description"):
                            ui.label(current["description"]).classes("text-sm text-slate-600")
                        with ui.row().classes("w-full justify-end"):
                            if closure is None:
                                delete_button = ui.button(
                                    "Delete", icon="delete_outline", color="negative",
                                    on_click=confirm_delete_current,
                                ).props("flat dense no-caps")
                                if children or records:
                                    delete_button.disable()
                                    delete_button.tooltip(
                                        "Remove or move all child aggregations and records before deleting"
                                    )
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
                    if closure:
                        with ui.card().classes("shadow-none border border-amber-200 bg-amber-50 min-w-[230px]"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("lock", color="amber-8")
                                ui.label("Closed").classes("font-semibold text-amber-900")
                            if closure["id"] == current["id"]:
                                ui.label("Closed directly").classes("text-xs text-amber-800")
                                ui.button(
                                    "Reopen aggregation", icon="lock_open",
                                    on_click=reopen_current,
                                ).props("flat dense no-caps color=primary").tooltip(
                                    "Clear the closure date; all other metadata remains unchanged"
                                )
                            else:
                                ui.label(
                                    f"Inherited from {closure['aggregation_number']} — {closure['title']}"
                                ).classes("text-xs text-amber-800")
                            ui.label(format_timestamp(closure.get("date_closed"))).classes("text-xs text-amber-700")
                    with ui.card().classes("shadow-none border border-slate-200 min-w-[150px]"):
                        ui.label(str(len(children))).classes("text-2xl font-bold text-primary")
                        ui.label("Child aggregations").classes("text-xs text-slate-500")
                    with ui.card().classes("shadow-none border border-slate-200 min-w-[150px]"):
                        ui.label(str(len(records))).classes("text-2xl font-bold text-primary")
                        ui.label("Records").classes("text-xs text-slate-500")

                if effective_rule:
                    with ui.card().classes("mx-5 mb-5 shadow-none border border-indigo-100 bg-indigo-50"):
                        with ui.row().classes("w-full items-center gap-3"):
                            ui.avatar(icon="schedule", color="indigo-1", text_color="indigo")
                            with ui.column().classes("gap-0 grow"):
                                ui.label("Effective retention rule").classes("font-semibold text-indigo-950")
                                if effective_rule["rule_source"] == "aggregation":
                                    source_text = "Specified locally for the governing root aggregation"
                                elif effective_rule.get("inheritance_depth", 0) == 0:
                                    source_text = "Specified by its classification"
                                else:
                                    source_text = "Inherited from an ancestor classification"
                                if current.get("parent_aggregation_id") is not None:
                                    governing_root_id = effective_rule["governing_root_aggregation_id"]
                                    governing_root = by_id.get(governing_root_id)
                                    if governing_root:
                                        root_reference = (
                                            f"{governing_root['aggregation_number']} — "
                                            f"{governing_root['title']}"
                                        )
                                    else:
                                        root_reference = f"#{governing_root_id}"
                                    source_text += (
                                        f" · governed by root aggregation {root_reference}"
                                    )
                                ui.label(source_text).classes("text-xs text-indigo-700")
                            ui.badge(effective_rule["final_disposition"].replace("_", " ").title(), color="indigo").props("outline")
                        with ui.row().classes("w-full gap-8 text-sm"):
                            ui.label(f"Current: {effective_rule['current_period_years']} years")
                            ui.label(f"Intermediate: {effective_rule['intermediate_period_years']} years")
                            if classification_path:
                                ui.label("Classification: " + " › ".join(
                                    f"{item['code']} — {item['title']}" for item in classification_path
                                )).classes("text-slate-600")
                        if effective_rule.get("instructions"):
                            ui.label(effective_rule["instructions"]).classes("text-sm text-slate-600")
                        if current.get("parent_aggregation_id") is None and closure is None:
                            with ui.row().classes("w-full justify-end"):
                                ui.button(
                                    "Edit local override" if local_retention_rule else "Set local override",
                                    icon="tune", on_click=manage_local_retention_rule,
                                ).props("flat dense no-caps color=primary")

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
                    record_table = ui.table(
                        columns=[
                            {"name": "record_number", "label": "Number", "field": "record_number", "align": "left"},
                            {"name": "title", "label": "Title", "field": "title", "align": "left"},
                            {"name": "date_originated", "label": "Originated", "field": "date_originated", "align": "left"},
                            {"name": "actions", "label": "", "field": "actions", "align": "right"},
                        ],
                        rows=records,
                        row_key="id",
                    ).props("flat separator=horizontal").classes("w-full")
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
            lifecycle_filter = None
            visible_rows = state["rows"]
            if spec.key in {"org-units", "roles", "users"}:
                status_options = {
                    "all": "All statuses",
                    "active": "Active",
                    "inactive": "Inactive",
                }
                if spec.key == "users":
                    status_options["suspended"] = "Suspended"
                with ui.row().classes("w-full items-center justify-end mb-2"):
                    lifecycle_filter = ui.select(
                        status_options,
                        value=state.get("lifecycle_filter", "all"),
                        label="Status",
                    ).props("outlined dense options-dense").classes("w-48")
                selected_status = lifecycle_filter.value
                if selected_status != "all":
                    visible_rows = [
                        row for row in state["rows"]
                        if row.get("effective_status", row.get("status")) == selected_status
                    ]
            columns = [
                {"name": key, "label": label, "field": key, "align": "left"}
                for key, label in spec.columns
            ]
            columns.append({"name": "actions", "label": "", "field": "actions", "align": "right"})
            if spec.key in {"aggregations", "records"}:
                for row in visible_rows:
                    row["_is_favourite"] = favourite_state(spec.key, row["id"])
            table = ui.table(columns=columns, rows=visible_rows, row_key="id", pagination=25).props("flat bordered separator=horizontal").classes("w-full")
            if lifecycle_filter is not None:
                def apply_lifecycle_filter() -> None:
                    state["lifecycle_filter"] = lifecycle_filter.value
                    selected = lifecycle_filter.value
                    table.rows = state["rows"] if selected == "all" else [
                        row for row in state["rows"]
                        if row.get("effective_status", row.get("status")) == selected
                    ]
                    table.update()

                lifecycle_filter.on_value_change(apply_lifecycle_filter)
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
                }.get(key, "link")
                relationship_template = """
                    <q-td :props="props">
                      <div v-if="props.value" class="row items-center no-wrap q-gutter-sm">
                        <q-avatar size="30px" color="blue-1" text-color="primary" icon="__ICON__" />
                        <div class="column">
                          <span class="text-weight-medium relationship-cell-name">{{ props.value.name }}</span>
                          <q-badge v-if="props.value.code" outline color="primary" :label="props.value.code" class="self-start" />
                        </div>
                      </div>
                      <span v-else class="text-grey-5">—</span>
                    </q-td>
                """.replace("__ICON__", relationship_icon)
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
            else:
                buttons = '<q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'
            if spec.key == "org-units":
                buttons = '<q-btn flat round dense icon="open_in_new" color="primary" @click="$parent.$emit(\'open_org_unit\', props.row)"><q-tooltip>Open organization unit</q-tooltip></q-btn>' + buttons
            if spec.key == "roles":
                buttons = '<q-btn flat round dense icon="open_in_new" color="primary" @click="$parent.$emit(\'open_role\', props.row)"><q-tooltip>Open role</q-tooltip></q-btn>' + buttons
            buttons += '<q-btn flat round dense icon="history" color="blue-grey" @click="$parent.$emit(\'history\', props.row)"><q-tooltip>Event history</q-tooltip></q-btn>'
            if spec.key == "records":
                buttons += '<q-btn flat round dense icon="attach_file" color="secondary" @click="$parent.$emit(\'components\', props.row)"><q-tooltip>Digital components</q-tooltip></q-btn>'
            if spec.key == "aggregations":
                buttons = '<q-btn flat round dense icon="folder_open" color="secondary" @click="$parent.$emit(\'open_aggregation\', props.row)"><q-tooltip>Open aggregation</q-tooltip></q-btn>' + buttons
                buttons += '<q-btn v-if="props.row._directly_closed" flat round dense icon="lock_open" color="primary" @click="$parent.$emit(\'reopen\', props.row)"><q-tooltip>Reopen aggregation</q-tooltip></q-btn>'
            if spec.key in {"users", "roles"}:
                buttons += '<q-btn flat round dense icon="group" color="secondary" @click="$parent.$emit(\'memberships\', props.row)"><q-tooltip>Role assignments</q-tooltip></q-btn>'
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
        auth_state["principal"] = principal
        user = principal["user"]
        current_user_name.text = user["name"]
        current_user_email.text = user.get("email") or user["account_type"].title()
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
        dialog = ui.dialog().props("persistent")
        with dialog, ui.card().classes("w-[480px] max-w-full"):
            ui.label("Change password").classes("text-xl font-semibold")
            current = ui.input("Current password", password=True, password_toggle_button=True).props("outlined").classes("w-full")
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

            with ui.row().classes("w-full justify-end"):
                if not (auth_state.get("principal") or {}).get("must_change_password"):
                    ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Change password", icon="password", on_click=save_password).props("unelevated")
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
            is_admin = any(role["code"].lower() == "system-administrator" for role in auth_state["principal"]["roles"])
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
                        f"Showing {len(rows)} sessions · {active_count} active"
                    ).classes("text-sm text-slate-500")
                    ui.space()
                    ui.button("Refresh", icon="refresh", on_click=load_sessions).props("flat no-caps")
                table = ui.table(
                    columns=[
                        {"name": "user_name", "label": "User", "field": "user_name", "align": "left"},
                        {"name": "status", "label": "Status", "field": "status", "align": "left"},
                        {"name": "date_created", "label": "Signed in", "field": "date_created", "align": "left"},
                        {"name": "last_seen_at", "label": "Last activity", "field": "last_seen_at", "align": "left"},
                        {"name": "expires_at", "label": "Expires", "field": "expires_at", "align": "left"},
                        {"name": "client_ip", "label": "IP address", "field": "client_ip", "align": "left"},
                        {"name": "user_agent", "label": "Client", "field": "user_agent", "align": "left"},
                        {"name": "actions", "label": "", "field": "actions", "align": "right"},
                    ], rows=rows, row_key="id", pagination=25,
                ).props("flat bordered wrap-cells").classes("w-full")
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
                      <q-btn v-if="props.row.status === 'active'" flat round dense color="negative" icon="logout" @click="$parent.$emit('revoke', props.row)"><q-tooltip>Force logout this session</q-tooltip></q-btn>
                      <q-btn v-if="props.row.status === 'active' && props.row.can_revoke_all" flat round dense color="negative" icon="phonelink_erase" @click="$parent.$emit('revoke_all', props.row)"><q-tooltip>Force logout all sessions for this user</q-tooltip></q-btn>
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
                        ui.label("Force logout?").classes("text-xl font-semibold")
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
                            ui.button("Force logout", icon="logout", color="negative", on_click=proceed).props("unelevated no-caps")
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
            dashboard_content = ui.column().classes("w-full p-5 gap-6")

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
                count_resources = [
                    "aggregations", "records", "classification-schemes",
                    "classifications", "org-units", "roles", "users", "event-history",
                ]
                count_results, scheme_rows, scheme_classification_counts, inactive_result, unclassified_result, favourites = await asyncio.gather(
                    asyncio.gather(*(api.count(resource) for resource in count_resources)),
                    api.list("classification-schemes"),
                    api.request("GET", "/api/v1/classification-schemes/classification-counts"),
                    api.search_request("classifications", {
                        "where": {"field": "date_deactivated", "operator": "is_not_null"},
                        "limit": 1,
                    }),
                    api.search_request("aggregations", {
                        "where": {"and": [
                            {"field": "parent_aggregation_id", "operator": "is_null"},
                            {"field": "classification_id", "operator": "is_null"},
                        ]},
                        "limit": 1,
                    }),
                    reload_favourites(),
                )
                current_user_id = auth_state["principal"]["user"]["id"]
                recent_limit = dashboard_recent_item_limit()
                recent_days = dashboard_recent_days()
                recent_since = datetime.now(timezone.utc) - timedelta(days=recent_days)
                recent_results = await asyncio.gather(
                    api.recently_created(
                        "aggregations", limit=recent_limit,
                        actor_user_id=current_user_id, since=recent_since,
                    ),
                    api.recently_updated(
                        "aggregations", limit=recent_limit,
                        actor_user_id=current_user_id, since=recent_since,
                    ),
                    api.recently_created(
                        "records", limit=recent_limit,
                        actor_user_id=current_user_id, since=recent_since,
                    ),
                    api.recently_updated(
                        "records", limit=recent_limit,
                        actor_user_id=current_user_id, since=recent_since,
                    ),
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
                    overview_cards = (
                        ("aggregations", "Aggregations", "folder", None, lambda: select_entity("aggregations")),
                        ("records", "Records", "description", None, lambda: select_entity("records")),
                        (
                            "classification-schemes", "Classification schemes", "account_tree",
                            f"{published_scheme_count} published · {draft_scheme_count} draft · "
                            f"{inactive_scheme_count} inactive",
                            select_classification_workspace,
                        ),
                        (
                            "classifications", "Classifications", "schema",
                            f"{branch_count} branches · {terminal_count} terminals\n"
                            f"{assignable_terminal_count} assignable terminals · "
                            f"{draft_terminal_count} draft terminals",
                            select_classification_workspace,
                        ),
                        ("org-units", "Organization units", "corporate_fare", None, lambda: select_entity("org-units")),
                        ("roles", "Roles", "badge", None, lambda: select_entity("roles")),
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
                            {
                                "aggregation": "Aggregation", "record": "Record",
                                "digital_component": "Digital component", "org_unit": "Organization unit",
                                "user": "User", "role": "Role", "user_role_assignment": "Role assignment",
                                "classification_scheme": "Classification scheme",
                                "classification": "Classification",
                                "classification_retention_rule": "Classification retention rule",
                                "aggregation_retention_rule": "Aggregation retention rule",
                            }, label="Entity type", clearable=True,
                        ).props("outlined dense").classes("w-full")
                        operation_filter = ui.select(
                            ["CREATE", "UPDATE", "DELETE", "CONTENT_UPLOADED", "CONTENT_REPLACED", "CONTENT_DELETED", "CONTENT_DOWNLOADED"],
                            label="Operation", clearable=True,
                        ).props("outlined dense use-input").classes("w-full")
                        source_filter = ui.input("Source").props("outlined dense clearable").classes("w-full")
                        actor_filter = ui.input("Actor type").props("outlined dense clearable").classes("w-full")
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

        async def load_audit_events() -> None:
            refresh_button.props("loading disable")
            conditions: list[dict[str, Any]] = []
            for field, operator, value in (
                ("entity_type", "eq", type_filter.value),
                ("operation", "eq", operation_filter.value),
                ("source", "eq", (source_filter.value or "").strip()),
                ("actor_type", "eq", (actor_filter.value or "").strip()),
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
        add_button.set_visibility(True)
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
                with ui.grid(columns=3).classes("w-full gap-4"):
                    for label, value in (
                        ("Direct status", role.get("status")), ("Effective status", role.get("effective_status")),
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
                    if not is_selector:
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
                    browser["roots"] = [{**item, "type": "org_unit"} for item in await api.organization_roots()]
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
        browser["roots"] = [{**item, "type": "org_unit"} for item in await api.organization_roots()]
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
        add_button.set_visibility(True)
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
    change_password_menu.on("click", show_change_password)
    my_sessions_menu.on("click", lambda: select_login_sessions())
    sign_out_menu.on("click", sign_out)
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
    with login_dialog, ui.card().classes("w-[460px] max-w-[calc(100vw-32px)] p-7 gap-4"):
        with ui.row().classes("items-center gap-3"):
            ui.avatar(icon="lock", color="blue-1", text_color="primary")
            with ui.column().classes("gap-0"):
                ui.label("Sign in to ERMS").classes("text-2xl font-semibold")
                ui.label("Use your organization credentials").classes("text-sm text-slate-500")
        login_email = ui.input("Email address").props("outlined autocomplete=username").classes("w-full")
        login_password = ui.input("Password", password=True, password_toggle_button=True).props("outlined autocomplete=current-password").classes("w-full")
        login_error = ui.label().classes("text-negative text-sm")

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
                await reload_favourites()
                login_password.value = ""
                login_dialog.close()
                if principal["must_change_password"]:
                    with table_container:
                        await show_change_password()
                else:
                    await select_dashboard()
            except ApiError as error:
                login_error.text = error_message(error)

        ui.button("Sign in", icon="login", on_click=submit_login).props("unelevated no-caps").classes("w-full")
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
        # NiceGUI adds body HTML dynamically, where script tags are inert.
        # Dynamic import executes the self-hosted module in the live page.
        await ui.run_javascript(
            "import('/static/pdfjs/erms-viewer.mjs').then(() => true)", timeout=15,
        )
        token = app.storage.user.get("session_token")
        if token:
            api.set_session_token(token)
            try:
                principal = await api.me()
                populate_user_menu(principal)
                await reload_favourites()
                if principal["must_change_password"]:
                    with table_container:
                        await show_change_password()
                elif navigation_state["trail"]:
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
        login_dialog.open()

    ui.timer(0.05, initialize_authenticated_ui, once=True)


def run() -> None:
    ui.run(
        title="ERMS",
        host=host(),
        port=port(),
        reload=reload_enabled(),
        storage_secret=storage_secret(),
        favicon="📚",
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
