from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from nicegui import app, background_tasks, events, ui

from .api_client import ApiError, ErmsApiClient
from .config import api_url, host, port, reload_enabled
from .entities import ENTITIES, EntitySpec, FieldSpec


api = ErmsApiClient(api_url())


@app.on_shutdown
async def close_api_client() -> None:
    await api.close()


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


def buffer_upload_batch(event: events.MultiUploadEventArguments) -> list[tuple[bytes, str, str]]:
    """Copy NiceGUI temporary uploads before any awaited API operation can release them."""
    return [
        (content_source.read(), name, mime_type or "application/octet-stream")
        for content_source, name, mime_type in zip(event.contents, event.names, event.types)
    ]


def render_component_cards(rows: list[dict[str, Any]], on_move, on_remove) -> None:
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
                        ui.button(icon="arrow_upward", on_click=lambda _, item=component: on_move(item, -1)).props(
                            "flat round dense" + (" disable" if index == 0 else "")
                        ).tooltip("Move earlier")
                        ui.button(icon="arrow_downward", on_click=lambda _, item=component: on_move(item, 1)).props(
                            "flat round dense" + (" disable" if index == len(rows) - 1 else "")
                        ).tooltip("Move later")
                        ui.button(icon="delete_outline", color="negative", on_click=lambda _, item=component: on_remove(item)).props("flat round dense").tooltip("Remove component")
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
    if field.kind == "textarea":
        return ui.textarea(field.label, value=value or "").props("outlined autogrow").classes("w-full")
    if field.kind == "int":
        return ui.number(field.label, value=value, format="%.0f").props("outlined").classes("w-full")
    if field.kind == "lookup":
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
        if field.kind in {"int", "lookup"} and value not in (None, ""):
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
    state: dict[str, Any] = {
        "resource": "org-units", "rows": [], "searched": False,
        "recent_created": [], "recent_updated": [], "aggregation_detail": None,
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
    """)

    with ui.header(elevated=True).classes("erms-header items-center gap-3"):
        ui.button(on_click=lambda: drawer.toggle(), icon="menu").props("flat round color=white")
        ui.icon("inventory_2").classes("text-2xl")
        ui.label("ERMS").classes("text-xl font-semibold tracking-wide")
        ui.space()
        connection_badge = ui.badge("API ready", color="positive").props("outline")

    with ui.left_drawer(value=True).classes("erms-drawer") as drawer:
        ui.label("RECORDS MANAGEMENT").classes("text-xs tracking-widest opacity-60 px-4 pt-5 pb-2")
        navigation: dict[str, Any] = {}
        for key, spec in ENTITIES.items():
            icon = {"aggregations": "folder", "records": "description", "org-units": "corporate_fare", "users": "group", "roles": "badge"}[key]
            navigation[key] = ui.button(spec.label, icon=icon).props("flat align=left").classes("w-full justify-start px-4")

    with ui.footer().classes("bg-white text-slate-500 border-t text-xs justify-between"):
        ui.label("Electronic Records Management System")
        ui.label("Initial administration interface")

    with ui.column().classes("erms-content w-full p-5 gap-4"):
        with ui.row().classes("w-full items-center"):
            with ui.column().classes("gap-0"):
                title = ui.label().classes("text-2xl font-semibold")
                subtitle = ui.label().classes("text-sm text-slate-500")
            ui.space()
            add_button = ui.button("Add", icon="add", color="primary").props("unelevated rounded")

        with ui.card().classes("erms-card w-full p-0"):
            with ui.row().classes("w-full items-end p-4 gap-2") as search_bar:
                search_input = ui.input("Search by number, title or description").props("outlined clearable").classes("grow")
                search_button = ui.button("Search", icon="search").props("unelevated")
            guidance = ui.label().classes("px-4 pb-4 text-slate-500")
            table_container = ui.column().classes("w-full gap-0")

    async def show_components(record: dict[str, Any]) -> None:
        current_rows: list[dict[str, Any]] = []
        upload_lock = asyncio.Lock()
        uploader_control: dict[str, Any] = {}

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
                uploader_control["uploader"] = component_uploader(uploaded)
                with ui.element("div").classes("component-list w-full mt-3"):
                    component_area = ui.element("div").classes("component-grid w-full")

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
                try:
                    await api.delete_component(component["id"], component["version"])
                    ui.notify("Digital component removed", color="positive")
                    await refresh_components()
                except ApiError as error:
                    ui.notify(error_message(error), color="negative")

            async def refresh_components() -> None:
                try:
                    rows = await api.components(record["id"])
                    current_rows.clear()
                    current_rows.extend(rows)
                    component_area.clear()
                    with component_area:
                        if not rows:
                            with ui.column().classes("w-full items-center py-8 gap-2 text-slate-400"):
                                ui.icon("cloud_upload").classes("text-4xl")
                                ui.label("No digital components uploaded yet.")
                        else:
                            render_component_cards(rows, move_component, remove_component)
                except ApiError as error:
                    ui.notify(error_message(error), color="negative")

            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        await refresh_components()
        dialog.open()

    async def show_record_details(record: dict[str, Any]) -> None:
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[720px] max-w-full"):
            with ui.row().classes("w-full items-start"):
                ui.avatar(icon="description", color="blue-1", text_color="primary")
                with ui.column().classes("gap-0 grow"):
                    ui.label(record["title"]).classes("text-xl font-semibold")
                    ui.label(record["record_number"]).classes("text-sm text-primary font-medium")
                ui.button(icon="close", on_click=dialog.close).props("flat round")
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
                ui.button(
                    "Digital components",
                    icon="attach_file",
                    on_click=lambda: show_components(record),
                ).props("outline")
        dialog.open()

    async def decorate_for_spec(
        spec: EntitySpec, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if spec.key == "org-units":
            return decorate_relationship_rows(spec.key, rows)
        if spec.key == "roles":
            return decorate_relationship_rows(spec.key, rows, await api.list("org-units"))
        if spec.key == "records":
            return decorate_relationship_rows(spec.key, rows, await api.list("aggregations"))
        return rows

    async def load_recent(spec: EntitySpec) -> None:
        if not spec.search_first:
            state["recent_created"] = []
            state["recent_updated"] = []
            return
        created, updated = await api.recently_created(spec.key), await api.recently_updated(spec.key)
        state["recent_created"] = await decorate_for_spec(spec, created)
        state["recent_updated"] = await decorate_for_spec(spec, updated)

    async def open_record_draft_editor() -> None:
        spec = ENTITIES["records"]
        try:
            draft = await api.create_record_draft()
            aggregations = await api.list("aggregations")
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
                await api.commit_record_draft(draft["id"])
                dialog.close()
                ui.notify("Record and digital components created", color="positive")
                await load_recent(spec)
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

    async def open_editor(row: dict[str, Any] | None = None) -> None:
        spec = ENTITIES[state["resource"]]
        creating = row is None
        if creating and spec.key == "records":
            await open_record_draft_editor()
            return
        lookup_options: dict[str, dict[int, str]] = {}
        try:
            for field in spec.fields:
                if not field.lookup_resource:
                    continue
                lookup_rows = await api.list(field.lookup_resource)
                if row and field.lookup_resource == spec.key:
                    lookup_rows = [item for item in lookup_rows if item["id"] != row["id"]]
                lookup_options[field.name] = relationship_options(
                    lookup_rows, field.lookup_label_fields
                )
        except ApiError as error:
            ui.notify(error_message(error), color="negative", close_button=True)
            return
        dialog = ui.dialog()
        controls: dict[str, Any] = {}
        with dialog, ui.card().classes("w-[620px] max-w-full"):
            ui.label(f"{'Add' if creating else 'Edit'} {spec.singular}").classes("text-xl font-semibold")
            with ui.column().classes("w-full gap-3"):
                for field in spec.fields:
                    controls[field.name] = field_input(
                        field,
                        None if creating else row.get(field.name),
                        lookup_options.get(field.name),
                    )

            async def save() -> None:
                try:
                    payload = form_payload(spec, controls, creating=creating)
                    if creating:
                        saved = await api.create(spec.key, payload)
                    else:
                        saved = await api.update(spec.key, row["id"], row["version"], payload)
                    dialog.close()
                    ui.notify(f"{spec.singular.capitalize()} saved", color="positive")
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
        assignments_area: Any = None
        selection_holder: dict[str, Any] = {}

        async def load_memberships() -> None:
            try:
                assignments = (
                    await api.user_roles(entity["id"])
                    if for_user else await api.role_users(entity["id"])
                )
                counterparts = await api.list(counterpart_resource)
                counterpart_by_id = {item["id"]: item for item in counterparts}
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
                            rows.append({
                                **assignment,
                                "counterpart": (
                                    f"{counterpart.get('code', '')} — {counterpart.get('name', counterpart_id)}"
                                    if for_user else counterpart.get("name", counterpart_id)
                                ),
                            })
                        membership_table = ui.table(
                            columns=[
                                {"name": "counterpart", "label": counterpart_label.capitalize(), "field": "counterpart", "align": "left"},
                                {"name": "valid_from", "label": "Valid from", "field": "valid_from", "align": "left"},
                                {"name": "valid_until", "label": "Valid until", "field": "valid_until", "align": "left"},
                                {"name": "actions", "label": "", "field": "actions", "align": "right"},
                            ],
                            rows=rows,
                            row_key="id",
                        ).props("flat bordered dense").classes("w-full")
                        add_timestamp_slots(membership_table, ["valid_from", "valid_until"])
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
            assignments_area = ui.column().classes("w-full")
            with ui.row().classes("w-full items-end gap-2"):
                selection_holder["control"] = relationship_select(
                    f"Select {counterpart_label}", {}
                ).classes("grow")
                ui.button("Assign", on_click=assign, icon="person_add").props("unelevated")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        dialog.open()
        await load_memberships()

    async def open_aggregation(aggregation: dict[str, Any]) -> None:
        try:
            all_aggregations = await api.list("aggregations")
            by_id = {item["id"]: item for item in all_aggregations}
            current = by_id.get(aggregation["id"], aggregation)
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
            state["aggregation_detail"] = current
            search_bar.set_visibility(False)
            guidance.text = ""
            title.text = current["title"]
            subtitle.text = current["aggregation_number"]
            table_container.clear()
            with table_container:
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
                    with ui.card().classes("shadow-none border border-slate-200 min-w-[150px]"):
                        ui.label(str(len(children))).classes("text-2xl font-bold text-primary")
                        ui.label("Child aggregations").classes("text-xs text-slate-500")
                    with ui.card().classes("shadow-none border border-slate-200 min-w-[150px]"):
                        ui.label(str(len(records))).classes("text-2xl font-bold text-primary")
                        ui.label("Records").classes("text-xs text-slate-500")

                if children:
                    ui.label("Contained aggregations").classes("px-5 text-base font-semibold")
                    with ui.grid(columns=3).classes("w-full px-5 pb-4 gap-3"):
                        for child in children:
                            with ui.card().classes("recent-card cursor-pointer p-4").on(
                                "click", lambda _, item=child: open_aggregation(item)
                            ):
                                with ui.row().classes("items-center no-wrap gap-3"):
                                    ui.avatar(icon="folder", color="blue-1", text_color="primary")
                                    with ui.column().classes("gap-0"):
                                        ui.label(child["title"]).classes("font-semibold")
                                        ui.label(child["aggregation_number"]).classes("text-xs text-slate-500")

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
                    record_table.add_slot("body-cell-actions", '<q-td :props="props"><q-btn flat round icon="open_in_new" color="primary" @click="$parent.$emit(\'open_record\', props.row)"><q-tooltip>Open record</q-tooltip></q-btn></q-td>')
                    record_table.on("open_record", lambda event: show_record_details(event.args))
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
                render_recent_section(spec)
                return
            columns = [
                {"name": key, "label": label, "field": key, "align": "left"}
                for key, label in spec.columns
            ]
            columns.append({"name": "actions", "label": "", "field": "actions", "align": "right"})
            table = ui.table(columns=columns, rows=state["rows"], row_key="id", pagination=25).props("flat bordered separator=horizontal").classes("w-full")
            add_timestamp_slots(
                table, [key for key, _ in spec.columns if key.startswith("date_")]
            )
            for key, _ in spec.columns:
                if not key.endswith("_display"):
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
            buttons = '<q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'
            if spec.key == "records":
                buttons += '<q-btn flat round dense icon="attach_file" color="secondary" @click="$parent.$emit(\'components\', props.row)"><q-tooltip>Digital components</q-tooltip></q-btn>'
            if spec.key == "aggregations":
                buttons = '<q-btn flat round dense icon="folder_open" color="secondary" @click="$parent.$emit(\'open_aggregation\', props.row)"><q-tooltip>Open aggregation</q-tooltip></q-btn>' + buttons
            if spec.key in {"users", "roles"}:
                buttons += '<q-btn flat round dense icon="group" color="secondary" @click="$parent.$emit(\'memberships\', props.row)"><q-tooltip>Role assignments</q-tooltip></q-btn>'
            table.add_slot("body-cell-actions", f'<q-td :props="props">{buttons}</q-td>')
            table.on("edit", lambda event: open_editor(event.args))
            if spec.key == "records":
                table.on("components", lambda event: show_components(event.args))
            if spec.key == "aggregations":
                table.on("open_aggregation", lambda event: open_aggregation(event.args))
            if spec.key in {"users", "roles"}:
                table.on(
                    "memberships",
                    lambda event, user_view=spec.key == "users": show_memberships(
                        event.args, for_user=user_view
                    ),
                )

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
            connection_badge.text = "API ready"
            connection_badge.props("color=positive")
            render_table(spec)
        except ApiError as error:
            connection_badge.text = "API unavailable"
            connection_badge.props("color=negative")
            ui.notify(error_message(error), color="negative", close_button=True)

    async def select_entity(key: str) -> None:
        state.update(resource=key, rows=[], searched=False, aggregation_detail=None)
        spec = ENTITIES[key]
        title.text = spec.label
        subtitle.text = "Search required before loading results" if spec.search_first else "Manage current system entries"
        search_bar.set_visibility(spec.search_first)
        guidance.text = "Large collections are search-first to avoid loading unbounded result sets." if spec.search_first else ""
        search_input.value = ""
        try:
            if spec.search_first:
                await load_recent(spec)
            render_table(spec)
            await load_rows()
        except ApiError as error:
            connection_badge.text = "API unavailable"
            connection_badge.props("color=negative")
            ui.notify(error_message(error), color="negative", close_button=True)

    for key, button in navigation.items():
        button.on("click", lambda _, entity_key=key: select_entity(entity_key))
    add_button.on("click", lambda: open_editor())
    search_button.on("click", lambda: load_rows())
    search_input.on("keydown.enter", lambda: load_rows())
    ui.timer(0.05, lambda: select_entity("org-units"), once=True)


def run() -> None:
    ui.run(
        title="ERMS",
        host=host(),
        port=port(),
        reload=reload_enabled(),
        favicon="📚",
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
