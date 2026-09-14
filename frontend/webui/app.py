from __future__ import annotations

from datetime import datetime
from typing import Any

from nicegui import app, events, ui

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


def error_message(error: ApiError) -> str:
    if error.status_code == 412:
        return "This item changed after you opened it. Reload it before saving again."
    if error.status_code == 428:
        return "The item version is missing. Reload it and try again."
    return error.message


def field_input(field: FieldSpec, value: Any = None):
    if field.kind == "textarea":
        return ui.textarea(field.label, value=value or "").props("outlined autogrow").classes("w-full")
    if field.kind == "int":
        return ui.number(field.label, value=value, format="%.0f").props("outlined").classes("w-full")
    if field.kind == "datetime":
        rendered = str(value or "")[:16]
        return ui.input(field.label, value=rendered).props("outlined type=datetime-local").classes("w-full")
    return ui.input(field.label, value=value or "").props("outlined").classes("w-full")


def form_payload(spec: EntitySpec, controls: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in spec.fields:
        value = controls[field.name].value
        if field.kind == "int" and value not in (None, ""):
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
    state: dict[str, Any] = {"resource": "org-units", "rows": [], "searched": False}

    ui.add_css("""
        :root { --erms-navy: #16324f; --erms-blue: #2563eb; --erms-bg: #f4f7fb; }
        body { background: var(--erms-bg); color: #172033; }
        .erms-header { background: var(--erms-navy); color: white; }
        .erms-drawer { background: #0f2740; color: #dce8f5; }
        .erms-content { max-width: 1500px; margin: 0 auto; }
        .erms-card { border: 1px solid #e2e8f0; box-shadow: 0 8px 28px rgba(15,39,64,.06); }
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
            icon = {"aggregations": "account_tree", "records": "description", "org-units": "corporate_fare", "users": "group", "roles": "badge"}[key]
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
        dialog = ui.dialog()
        with dialog, ui.card().classes("w-[760px] max-w-full"):
            ui.label(f"Digital components — {record['record_number']}").classes("text-lg font-semibold")
            component_area = ui.column().classes("w-full")
            order = ui.number("Component order", value=1, min=1, format="%.0f").props("outlined")

            async def refresh_components() -> None:
                try:
                    rows = await api.components(record["id"])
                    component_area.clear()
                    with component_area:
                        if not rows:
                            ui.label("No digital components uploaded.").classes("text-slate-500")
                        else:
                            ui.table(
                                columns=[{"name": k, "label": label, "field": k} for k, label in (("component_order", "Order"), ("file_name", "File"), ("mime_type", "MIME type"), ("size_in_bytes", "Bytes"), ("content_status", "Status"))],
                                rows=rows,
                                row_key="id",
                            ).props("flat dense").classes("w-full")
                except ApiError as error:
                    ui.notify(error_message(error), color="negative")

            async def uploaded(event: events.UploadEventArguments) -> None:
                try:
                    file_object = getattr(event, "file", None)
                    if file_object is not None:
                        content = await file_object.read()
                        name = file_object.name
                        mime_type = file_object.content_type or "application/octet-stream"
                    else:
                        content = event.content.read()
                        name = event.name
                        mime_type = event.type or "application/octet-stream"
                    await api.upload_component(record["id"], int(order.value), name, content, mime_type)
                    ui.notify("Digital component uploaded", color="positive")
                    await refresh_components()
                except ApiError as error:
                    ui.notify(error_message(error), color="negative")

            ui.upload(on_upload=uploaded, label="Choose a file", auto_upload=True).props("accept=* max-files=1").classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat")
        await refresh_components()
        dialog.open()

    async def open_editor(row: dict[str, Any] | None = None) -> None:
        spec = ENTITIES[state["resource"]]
        creating = row is None
        dialog = ui.dialog()
        controls: dict[str, Any] = {}
        with dialog, ui.card().classes("w-[620px] max-w-full"):
            ui.label(f"{'Add' if creating else 'Edit'} {spec.singular}").classes("text-xl font-semibold")
            with ui.column().classes("w-full gap-3"):
                for field in spec.fields:
                    controls[field.name] = field_input(field, None if creating else row.get(field.name))

            async def save() -> None:
                try:
                    payload = form_payload(spec, controls, creating=creating)
                    if creating:
                        await api.create(spec.key, payload)
                    else:
                        await api.update(spec.key, row["id"], row["version"], payload)
                    dialog.close()
                    ui.notify(f"{spec.singular.capitalize()} saved", color="positive")
                    await load_rows(repeat_search=True)
                except ValueError as error:
                    ui.notify(str(error), color="warning")
                except ApiError as error:
                    ui.notify(error_message(error), color="negative", close_button=True)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save", on_click=save, icon="save").props("unelevated")
        dialog.open()

    def render_table(spec: EntitySpec) -> None:
        table_container.clear()
        with table_container:
            if spec.search_first and not state["searched"]:
                ui.label(f"Search for {spec.label.lower()} to display results.").classes("p-8 self-center text-slate-500")
                return
            columns = [
                {"name": key, "label": label, "field": key, "align": "left"}
                for key, label in spec.columns
            ]
            columns.append({"name": "actions", "label": "", "field": "actions", "align": "right"})
            table = ui.table(columns=columns, rows=state["rows"], row_key="id", pagination=25).props("flat bordered separator=horizontal").classes("w-full")
            buttons = '<q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit(\'edit\', props.row)"><q-tooltip>Edit</q-tooltip></q-btn>'
            if spec.key == "records":
                buttons += '<q-btn flat round dense icon="attach_file" color="secondary" @click="$parent.$emit(\'components\', props.row)"><q-tooltip>Digital components</q-tooltip></q-btn>'
            table.add_slot("body-cell-actions", f'<q-td :props="props">{buttons}</q-td>')
            table.on("edit", lambda event: open_editor(event.args))
            if spec.key == "records":
                table.on("components", lambda event: show_components(event.args))

    async def load_rows(*, repeat_search: bool = False) -> None:
        spec = ENTITIES[state["resource"]]
        try:
            if spec.search_first:
                query = (search_input.value or "").strip()
                if not query and not repeat_search:
                    state["searched"] = False
                    state["rows"] = []
                elif query:
                    state["rows"] = await api.search(spec.key, query, spec.search_fields)
                    state["searched"] = True
            else:
                state["rows"] = await api.list(spec.key)
                state["searched"] = True
            connection_badge.text = "API ready"
            connection_badge.props("color=positive")
            render_table(spec)
        except ApiError as error:
            connection_badge.text = "API unavailable"
            connection_badge.props("color=negative")
            ui.notify(error_message(error), color="negative", close_button=True)

    async def select_entity(key: str) -> None:
        state.update(resource=key, rows=[], searched=False)
        spec = ENTITIES[key]
        title.text = spec.label
        subtitle.text = "Search required before loading results" if spec.search_first else "Manage current system entries"
        search_bar.set_visibility(spec.search_first)
        guidance.text = "Large collections are search-first to avoid loading unbounded result sets." if spec.search_first else ""
        search_input.value = ""
        render_table(spec)
        await load_rows()

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
