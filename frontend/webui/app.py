from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nicegui import app, background_tasks, context, events, ui

from .api_client import ApiError, ErmsApiClient
from .config import (
    api_url,
    dashboard_recent_days,
    dashboard_recent_item_limit,
    classification_recent_selection_limit,
    host,
    port,
    reload_enabled,
    storage_secret,
)
from .entities import ENTITIES, EntitySpec, FieldSpec


app.add_static_files("/static/pdfjs", Path(__file__).with_name("static") / "pdfjs")


def display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str) and "T" in value:
        return value.replace("T", " ").replace("+00:00", "Z")[:19]
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
            {"human": "Human user", "service": "Service account"},
            label=field.label, value=value or "human",
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
        "lifecycle_filter": "all",
    }

    ui.add_css("""
        :root { --erms-navy: #16324f; --erms-blue: #2563eb; --erms-bg: #f4f7fb; }
        body { background: var(--erms-bg); color: #172033; }
        .erms-header { background: var(--erms-navy); color: white; }
        .erms-drawer { background: #0f2740; color: #dce8f5; }
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
        .audit-event { border-left: 3px solid #bfdbfe; box-shadow: none; }
        .audit-event:hover { border-left-color: #3b82f6; background: #f8fbff; }
        .audit-value { max-width: 360px; overflow-wrap: anywhere; white-space: pre-wrap; }
        .dashboard-stat { border: 1px solid #e2e8f0; box-shadow: none; transition: all .16s ease; }
        .dashboard-stat:hover { border-color: #93b4e8; transform: translateY(-2px); box-shadow: 0 8px 22px rgba(37,99,235,.08); }
    """)

    with ui.header(elevated=True).classes("erms-header items-center gap-3"):
        ui.button(on_click=lambda: drawer.toggle(), icon="menu").props("flat round color=white")
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

    def drawer_link(label: str, icon: str, *, extra_classes: str = "") -> tuple[Any, Any]:
        with ui.button(icon=icon).props("flat align=left no-caps").classes(
            f"w-full justify-start px-4 {extra_classes}"
        ) as button:
            ui.label(label).classes("grow text-left")
            badge = ui.badge("—", color="blue-grey").props("rounded")
        return button, badge

    with ui.left_drawer(value=True).classes("erms-drawer") as drawer:
        navigation: dict[str, Any] = {}
        navigation_badges: dict[str, Any] = {}
        dashboard_navigation = ui.button("Dashboard", icon="dashboard").props("flat align=left no-caps").classes("w-full justify-start px-4 mt-4")
        for heading, entries in (
            ("RECORDS MANAGEMENT", (("aggregations", "folder"), ("records", "description"), ("classification-schemes", "account_tree"), ("classifications", "label"))),
            ("ORGANIZATION STRUCTURE", (("org-units", "corporate_fare"), ("roles", "badge"), ("users", "group"))),
        ):
            ui.label(heading).classes("text-xs tracking-widest opacity-60 px-4 pt-5 pb-2")
            for key, icon in entries:
                navigation[key], navigation_badges[key] = drawer_link(ENTITIES[key].label, icon)
        ui.label("SYSTEM ADMINISTRATION").classes("text-xs tracking-widest opacity-60 px-4 pt-5 pb-2")
        audit_navigation, navigation_badges["event-history"] = drawer_link("Audit trail", "manage_history")
        sessions_navigation, navigation_badges["login-sessions"] = drawer_link("Login sessions", "devices")

    with ui.column().classes("erms-content w-full p-5 gap-4"):
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
            with ui.row().classes("w-full items-end p-4 gap-2") as search_bar:
                search_input = ui.input("Search by number, title or description").props("outlined clearable").classes("grow")
                search_button = ui.button("Search", icon="search").props("unelevated")
            guidance = ui.label().classes("px-4 pb-4 text-slate-500")
            table_container = ui.column().classes("w-full gap-0")
    content_card.set_visibility(False)
    add_button.set_visibility(False)
    add_record_button.set_visibility(False)

    def clear_authenticated_view() -> None:
        """Remove protected data as soon as there is no authenticated principal."""
        state.update(resource="dashboard", rows=[], searched=False, aggregation_detail=None)
        title.text = ""
        subtitle.text = ""
        guidance.text = ""
        table_container.clear()
        search_bar.set_visibility(False)
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        content_card.set_visibility(False)
        for badge in navigation_badges.values():
            badge.text = "—"
            badge.update()

    def show_authenticated_view() -> None:
        content_card.set_visibility(True)

    entity_types = {
        "aggregations": "aggregation", "records": "record",
        "digital-components": "digital_component", "org-units": "org_unit",
        "users": "user", "roles": "role",
        "classification-schemes": "classification_scheme",
        "classifications": "classification",
    }

    async def refresh_navigation_counts() -> None:
        resources = ["aggregations", "records", "classification-schemes", "classifications", "org-units", "roles", "users", "event-history"]
        try:
            counts = await asyncio.gather(*(api.count(resource) for resource in resources))
            for resource, count in zip(resources, counts):
                navigation_badges[resource].text = str(count)
                navigation_badges[resource].update()
            sessions = await api.login_sessions()
            navigation_badges["login-sessions"].text = str(sum(row["status"] == "active" for row in sessions))
            navigation_badges["login-sessions"].update()
            set_connection_status(True)
        except ApiError as error:
            # An HTTP response, including 401, means the API is reachable.
            set_connection_status(error.status_code != 503)

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
            with table_container:
                await show_record_details(entity)
        elif entity_type == "digital_component":
            try:
                record = await api.get("records", entity["record_id"])
                with table_container:
                    await show_components(record)
            except ApiError as error:
                ui.notify(error_message(error), color="negative", close_button=True)
        elif entity_type in {"org_unit", "user", "role", "classification_scheme", "classification"}:
            resource = {
                "org_unit": "org-units", "user": "users", "role": "roles",
                "classification_scheme": "classification-schemes",
                "classification": "classifications",
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

    async def show_components(record: dict[str, Any]) -> None:
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
                        await refresh_components()
                        first_position = len(current_rows) + 1
                        for offset, (content, name, mime_type) in enumerate(buffered_files):
                            await api.upload_component(
                                record["id"], first_position + offset, name, content, mime_type,
                            )
                            await refresh_components()
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

        dialog = ui.dialog()
        with dialog, ui.card().classes("max-h-[calc(100vh-32px)]").style("width: 920px; max-width: calc(100vw - 32px)"):
            with ui.row().classes("w-full items-start no-wrap"):
                with ui.column().classes("gap-0 grow"):
                    ui.label("Digital components").classes("text-xl font-semibold")
                    ui.label(f"Record {record['record_number']}").classes("text-sm text-slate-500")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense")
            with ui.element("div").classes("w-full overflow-y-auto max-h-[calc(100vh-190px)] pr-1"):
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

            def render_current_components() -> None:
                component_area.clear()
                with component_area:
                    if not current_rows:
                        with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                            ui.icon("cloud_upload").classes("text-4xl")
                            ui.label("No digital components uploaded yet.")
                    else:
                        render_component_cards(
                            current_rows, move_component, remove_component,
                            lambda item: show_entity_history("digital-components", item),
                            view_component, download_component, readonly=readonly,
                        )

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

            async def refresh_components() -> None:
                try:
                    rows = await api.components(record["id"])
                    current_rows.clear()
                    current_rows.extend(rows)
                    render_current_components()
                except ApiError as error:
                    ui.notify(error_message(error), color="negative")

            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        await refresh_components()
        dialog.open()

    async def show_record_details(record: dict[str, Any]) -> None:
        dialog = ui.dialog()

        async def refresh_record_view(saved: dict[str, Any] | None = None) -> None:
            dialog.close()
            aggregation_context = state.get("aggregation_detail")
            if aggregation_context:
                await open_aggregation(aggregation_context)
            elif state.get("resource") == "dashboard":
                await select_dashboard()
            else:
                await select_entity("records")
            if saved is not None:
                decorated = await decorate_for_spec(ENTITIES["records"], [saved])
                await show_record_details(decorated[0])

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
                        await refresh_navigation_counts()
                        await load_recent(ENTITIES["records"])
                        await refresh_record_view()
                    except ApiError as error:
                        ui.notify(error_message(error), color="negative", close_button=True)

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("Cancel", on_click=confirmation.close).props("flat no-caps")
                    ui.button(
                        "Delete record", icon="delete_forever", color="negative",
                        on_click=delete_record,
                    ).props("unelevated no-caps")
            confirmation.open()

        with dialog, ui.card().classes("w-[720px] max-w-full"):
            with ui.row().classes("w-full items-start"):
                ui.avatar(icon="description", color="blue-1", text_color="primary")
                with ui.column().classes("gap-0 grow"):
                    ui.label(record["title"]).classes("text-xl font-semibold")
                    ui.label(record["record_number"]).classes("text-sm text-primary font-medium")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
            if record.get("_effectively_closed"):
                with ui.row().classes("w-full items-center gap-2 p-2 bg-amber-50 border border-amber-200 rounded-lg"):
                    ui.icon("lock", color="amber-8")
                    ui.label("This record is read-only because its aggregation hierarchy is closed.").classes("text-sm text-amber-900")
            if record.get("description"):
                ui.label(record["description"]).classes("text-slate-600")
            with ui.row().classes("w-full gap-8 text-sm"):
                with ui.column().classes("gap-0"):
                    ui.label("Originated").classes("text-xs text-slate-400 uppercase")
                    ui.label(format_timestamp(record.get("date_originated"))).classes("font-medium text-slate-700")
                with ui.column().classes("gap-0"):
                    ui.label("Created").classes("text-xs text-slate-400 uppercase")
                    ui.label(format_timestamp(record.get("date_created"))).classes("font-medium text-slate-700")
            with ui.row().classes("w-full justify-end"):
                if not record.get("_effectively_closed"):
                    ui.button(
                        "Delete", icon="delete_outline", color="negative",
                        on_click=confirm_delete_record,
                    ).props("flat")
                    ui.button(
                        "Edit", icon="edit",
                        on_click=lambda: open_editor(
                            record, on_saved=refresh_record_view,
                            resource_key="records",
                        ),
                    ).props("flat")
                ui.button(
                    "Event history", icon="history",
                    on_click=lambda: show_entity_history("records", record),
                ).props("flat")
                ui.button(
                    "Digital components",
                    icon="attach_file",
                    on_click=lambda: show_components(record),
                ).props("outline")
        dialog.open()

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
            return [{
                **item,
                "effective_status": item.get("status"),
                "_inactive_reason": item.get("status", "active").title(),
            } for item in rows]
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
                with component_area:
                    if rows:
                        render_component_cards(rows, move_draft_component, remove_draft_component)
                    else:
                        with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                            ui.icon("upload_file").classes("text-4xl")
                            ui.label("Add one or more files before creating the record.")
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
                await refresh_navigation_counts()
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
                with ui.element("div").classes("component-list w-full mt-3"):
                    component_area = ui.element("div").classes("component-grid w-full")
            ui.separator()
            with ui.row().classes("w-full justify-end gap-2 px-6 py-4"):
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
        spec = ENTITIES[resource_key or state["resource"]]
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
                retention_rule = await api.classification_retention_rule(row["id"])
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
                                item.get("code"), item.get("title"), item.get("description"),
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
                            with ui.row().classes("w-full items-center gap-3"):
                                ui.avatar(icon="account_tree", color="blue-1", text_color="primary")
                                with ui.column().classes("gap-0 grow"):
                                    ui.label(scheme["title"]).classes("font-semibold")
                                    ui.label(scheme["code"]).classes("text-xs text-primary")
                                    if scheme.get("description"):
                                        ui.label(scheme["description"]).classes("text-xs text-slate-500 line-clamp-2")
                                ui.icon("chevron_right").classes("text-slate-400")

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
                                    icon="label" if classification["is_terminal"] else "account_tree",
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
                    if field.name in (locked_fields or set()):
                        controls[field.name].disable()
                    if spec.key == "aggregations" and field.name == "classification_id":
                        parent_id = (initial_values or {}).get("parent_aggregation_id") if creating else row.get("parent_aggregation_id")
                        if parent_id is not None:
                            controls[field.name].value = None
                            controls[field.name].disable()
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
                    if creating:
                        await refresh_navigation_counts()
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
                                "counterpart_status": effective_status,
                                "counterpart_status_reason": inactive_reason,
                            })
                        membership_table = ui.table(
                            columns=[
                                {"name": "counterpart", "label": counterpart_label.capitalize(), "field": "counterpart", "align": "left"},
                                {"name": "counterpart_status", "label": "Status", "field": "counterpart_status", "align": "left"},
                                {"name": "valid_from", "label": "Valid from", "field": "valid_from", "align": "left"},
                                {"name": "valid_until", "label": "Valid until", "field": "valid_until", "align": "left"},
                                {"name": "actions", "label": "", "field": "actions", "align": "right"},
                            ],
                            rows=rows,
                            row_key="id",
                        ).props("flat bordered dense").classes("w-full")
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

        with dialog, ui.card().classes("w-[820px] max-w-full"):
            heading = entity.get("name") or entity.get("code") or entity["id"]
            ui.label(f"{counterpart_label.capitalize()} assignments — {heading}").classes("text-xl font-semibold")
            if not assignment_allowed:
                with ui.row().classes("w-full items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg"):
                    ui.icon("block", color="amber-8")
                    ui.label(
                        "New assignments are unavailable while this user or role is ineffective. Existing assignments remain visible."
                    ).classes("text-sm text-amber-900")
            assignments_area = ui.column().classes("w-full")
            with ui.row().classes("w-full items-end gap-2"):
                selection_holder["control"] = relationship_select(
                    f"Select {counterpart_label}", {}
                ).classes("grow")
                assign_button = ui.button("Assign", on_click=assign, icon="person_add").props("unelevated")
                if not assignment_allowed:
                    selection_holder["control"].disable()
                    assign_button.disable()
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()
        await load_memberships()

    async def open_aggregation(aggregation: dict[str, Any]) -> None:
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
            guidance.text = ""
            title.text = current["title"]
            subtitle.text = current["aggregation_number"]
            table_container.clear()
            with table_container:
                async def reopen_current() -> None:
                    try:
                        reopened = await api.update(
                            "aggregations", current["id"], current["version"],
                            {"date_closed": None},
                        )
                        ui.notify("Aggregation reopened", color="positive")
                        await refresh_navigation_counts()
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
                                await refresh_navigation_counts()
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

                with ui.row().classes("w-full p-5 gap-4"):
                    with ui.card().classes("bg-blue-50 border border-blue-100 shadow-none grow"):
                        with ui.row().classes("items-center gap-3"):
                            ui.avatar(icon="folder", color="primary", text_color="white")
                            with ui.column().classes("gap-0"):
                                ui.label(current["aggregation_number"]).classes("text-xs text-primary font-semibold")
                                ui.label(current["title"]).classes("text-lg font-semibold")
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
                                        current, on_saved=open_aggregation
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
                                    source_text += f" · governed by root aggregation #{effective_rule['governing_root_aggregation_id']}"
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
                                    if child_closure:
                                        ui.badge("Closed", color="amber-8").props("outline")

                ui.label("Records in this aggregation").classes("px-5 pt-2 text-base font-semibold")
                if not records:
                    ui.label("This aggregation does not contain any records.").classes("px-5 pb-6 text-slate-500")
                else:
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
                    record_table.add_slot("body-cell-actions", '<q-td :props="props"><q-btn flat round icon="open_in_new" color="primary" @click="$parent.$emit(\'open_record\', props.row)"><q-tooltip>Open record</q-tooltip></q-btn><q-btn flat round icon="history" color="blue-grey" @click="$parent.$emit(\'history\', props.row)"><q-tooltip>Event history</q-tooltip></q-btn></q-td>')
                    record_table.on("open_record", lambda event: show_record_details(event.args))
                    record_table.on("history", lambda event: show_entity_history("records", event.args))
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

    def render_table(spec: EntitySpec) -> None:
        table_container.clear()
        with table_container:
            if spec.search_first and not state["searched"]:
                if spec.key == "classifications":
                    with ui.column().classes("w-full items-center py-12 gap-2 text-slate-500"):
                        ui.icon("manage_search", size="42px").classes("text-primary")
                        ui.label("Search classifications by code, title, or description.").classes("font-medium")
                        ui.label("Use * for any number of characters and ? for one character.").classes("text-xs")
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
            for key, _ in spec.columns:
                if not key.endswith("_display"):
                    continue
                if key == "type_display":
                    table.add_slot("body-cell-type_display", """
                        <q-td :props="props">
                          <div class="row items-center no-wrap q-gutter-sm">
                            <q-avatar size="30px" color="blue-1" text-color="primary" :icon="props.row.is_terminal ? 'label' : 'account_tree'" />
                            <span class="text-weight-medium">{{ props.row.is_terminal ? 'Terminal' : 'Branch' }}</span>
                          </div>
                        </q-td>
                    """)
                    continue
                table.add_slot(f"body-cell-{key}", """
                    <q-td :props="props">
                      <div v-if="props.value" class="row items-center no-wrap q-gutter-sm">
                        <q-avatar size="30px" color="blue-1" text-color="primary" icon="account_tree" />
                        <div class="column">
                          <span class="text-weight-medium relationship-cell-name">{{ props.value.name }}</span>
                          <q-badge v-if="props.value.code" outline color="primary" :label="props.value.code" class="self-start" />
                        </div>
                      </div>
                      <span v-else class="text-grey-5">—</span>
                    </q-td>
                """)
            if any(key == "effective_status" for key, _ in spec.columns):
                table.add_slot("body-cell-effective_status", '''
                    <q-td :props="props">
                      <q-badge
                        :color="props.value === 'active' ? 'positive' : (props.value === 'suspended' ? 'warning' : 'grey-7')"
                        :label="props.value"
                      ><q-tooltip>{{ props.row._inactive_reason }}</q-tooltip></q-badge>
                    </q-td>
                ''')
            if spec.key in {"records", "aggregations"}:
                closed_label = f"Closed {spec.singular} metadata cannot be changed"
                buttons = f'<q-btn flat round dense icon="edit" color="primary" :disable="props.row._effectively_closed" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>{{{{ props.row._effectively_closed ? \'{closed_label}\' : \'Edit\' }}}}</q-tooltip></q-btn>'
            else:
                buttons = '<q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'
            buttons += '<q-btn flat round dense icon="history" color="blue-grey" @click="$parent.$emit(\'history\', props.row)"><q-tooltip>Event history</q-tooltip></q-btn>'
            if spec.key == "records":
                buttons += '<q-btn flat round dense icon="attach_file" color="secondary" @click="$parent.$emit(\'components\', props.row)"><q-tooltip>Digital components</q-tooltip></q-btn>'
            if spec.key == "aggregations":
                buttons = '<q-btn flat round dense icon="folder_open" color="secondary" @click="$parent.$emit(\'open_aggregation\', props.row)"><q-tooltip>Open aggregation</q-tooltip></q-btn>' + buttons
                buttons += '<q-btn v-if="props.row._directly_closed" flat round dense icon="lock_open" color="primary" @click="$parent.$emit(\'reopen\', props.row)"><q-tooltip>Reopen aggregation</q-tooltip></q-btn>'
            if spec.key in {"users", "roles"}:
                buttons += '<q-btn flat round dense icon="group" color="secondary" @click="$parent.$emit(\'memberships\', props.row)"><q-tooltip>Role assignments</q-tooltip></q-btn>'
            if spec.key == "users":
                buttons += '<q-btn flat round dense icon="password" color="orange" @click="$parent.$emit(\'temporary_password\', props.row)"><q-tooltip>Issue temporary password</q-tooltip></q-btn>'
            if spec.key in {"org-units", "roles", "users"}:
                buttons += '<q-btn flat round dense :icon="props.row.status === \'inactive\' ? \'toggle_on\' : \'toggle_off\'" :color="props.row.status === \'inactive\' ? \'positive\' : \'negative\'" @click="$parent.$emit(\'lifecycle\', props.row)"><q-tooltip>{{ props.row.status === \'inactive\' ? \'Activate\' : \'Deactivate\' }}</q-tooltip></q-btn>'
            if spec.key == "classification-schemes":
                buttons += '<q-btn v-if="!props.row.date_published" flat round dense icon="publish" color="primary" @click="$parent.$emit(\'publish_scheme\', props.row)"><q-tooltip>Publish now</q-tooltip></q-btn>'
                buttons += '<q-btn flat round dense :icon="props.row.date_deactivated ? \'toggle_on\' : \'toggle_off\'" :color="props.row.date_deactivated ? \'positive\' : \'negative\'" @click="$parent.$emit(\'scheme_lifecycle\', props.row)"><q-tooltip>{{ props.row.date_deactivated ? \'Reactivate\' : \'Deactivate\' }}</q-tooltip></q-btn>'
            table.add_slot("body-cell-actions", f'<q-td :props="props">{buttons}</q-td>')
            table.on("edit", lambda event: open_editor(event.args))
            table.on("history", lambda event, resource=spec.key: show_entity_history(resource, event.args))
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
                                    auth_state["principal"] = None
                                    clear_authenticated_view()
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
        try:
            await api.logout()
        except ApiError:
            pass
        app.storage.user.pop("session_token", None)
        api.set_session_token(None)
        auth_state["principal"] = None
        clear_authenticated_view()
        login_dialog.open()

    async def select_login_sessions() -> None:
        show_authenticated_view()
        state.update(resource="login-sessions", rows=[], searched=True, aggregation_detail=None)
        title.text = "Login sessions"
        subtitle.text = "Review and revoke authenticated sessions"
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        with table_container:
            outer = ui.column().classes("w-full p-5 gap-4")

        async def load_sessions() -> None:
            try:
                rows = await api.login_sessions()
            except ApiError as error:
                ui.notify(error_message(error), color="negative")
                return
            active_count = sum(row["status"] == "active" for row in rows)
            is_admin = any(role["code"].lower() == "system-administrator" for role in auth_state["principal"]["roles"])
            for row in rows:
                row["can_revoke_all"] = is_admin
            navigation_badges["login-sessions"].text = str(active_count)
            navigation_badges["login-sessions"].update()
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
                      <div class="column">
                        <span class="text-weight-medium">{{ props.row.user_name }}</span>
                        <span class="text-caption text-grey-6">{{ props.row.user_email || 'No email address' }}</span>
                        <q-badge v-if="props.row.is_current" outline color="primary" label="Current session" class="self-start q-mt-xs" />
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
        show_authenticated_view()
        state.update(resource="dashboard", rows=[], searched=True, aggregation_detail=None)
        title.text = "Dashboard"
        subtitle.text = "An overview of your records management system"
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
        guidance.text = ""
        table_container.clear()
        with table_container:
            dashboard_content = ui.column().classes("w-full p-5 gap-6")

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
                count_resources = ["aggregations", "records", "org-units", "roles", "users", "event-history"]
                count_results = await asyncio.gather(
                    *(api.count(resource) for resource in count_resources),
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
                sessions = await api.login_sessions()
                active_session_count = sum(row["status"] == "active" for row in sessions)
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
                with ui.grid(columns=5).classes("w-full gap-3"):
                    for resource, label, icon in (
                        ("aggregations", "Aggregations", "folder"),
                        ("records", "Records", "description"),
                        ("org-units", "Organization units", "corporate_fare"),
                        ("roles", "Roles", "badge"),
                        ("users", "Users", "group"),
                    ):
                        with ui.card().classes("dashboard-stat cursor-pointer p-4 gap-2").on(
                            "click", lambda _, key=resource: select_entity(key)
                        ):
                            with ui.row().classes("items-center gap-3 no-wrap"):
                                ui.avatar(icon=icon, color="blue-1", text_color="primary")
                                with ui.column().classes("gap-0"):
                                    ui.label(str(counts[resource])).classes("text-2xl font-bold text-slate-800")
                                    ui.label(label).classes("text-xs text-slate-500")

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
                for resource, count in counts.items():
                    navigation_badges[resource].text = str(count)
                    navigation_badges[resource].update()
                navigation_badges["login-sessions"].text = str(active_session_count)
                navigation_badges["login-sessions"].update()
                set_connection_status(True)

        await load_dashboard()

    async def select_audit_trail() -> None:
        show_authenticated_view()
        state.update(resource="audit-trail", rows=[], searched=True, aggregation_detail=None)
        title.text = "Audit trail"
        subtitle.text = "Immutable history of changes across the system"
        add_button.set_visibility(False)
        add_record_button.set_visibility(False)
        search_bar.set_visibility(False)
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
            set_connection_status(error.status_code != 503)
            ui.notify(error_message(error), color="negative", close_button=True)

    async def select_entity(key: str) -> None:
        show_authenticated_view()
        state.update(
            resource=key, rows=[], searched=False, aggregation_detail=None,
            lifecycle_filter="all",
        )
        spec = ENTITIES[key]
        title.text = spec.label
        subtitle.text = "Search required before loading results" if spec.search_first else "Manage current system entries"
        search_bar.set_visibility(spec.search_first)
        guidance.text = "Large collections are search-first to avoid loading unbounded result sets." if spec.search_first else ""
        add_button.set_visibility(True)
        add_button.text = "Add"
        add_button.update()
        add_record_button.set_visibility(False)
        search_input.value = ""
        try:
            if spec.search_first:
                await load_recent(spec)
            render_table(spec)
            await load_rows()
        except ApiError as error:
            set_connection_status(error.status_code != 503)
            ui.notify(error_message(error), color="negative", close_button=True)

    for key, button in navigation.items():
        button.on("click", lambda _, entity_key=key: select_entity(entity_key))
    dashboard_navigation.on("click", select_dashboard)
    audit_navigation.on("click", select_audit_trail)
    sessions_navigation.on("click", select_login_sessions)
    change_password_menu.on("click", show_change_password)
    my_sessions_menu.on("click", select_login_sessions)
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
            on_saved=refresh_parent,
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
        auth_state["principal"] = None
        current_user_name.text = "Not signed in"
        current_user_email.text = ""
        current_user_roles.clear()
        clear_authenticated_view()
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
                if principal["must_change_password"]:
                    with table_container:
                        await show_change_password()
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
