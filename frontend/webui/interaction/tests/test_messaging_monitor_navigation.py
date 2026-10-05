"""Click the Monitor button using the application's actual navigation wiring."""

import ast
import inspect
import json
from pathlib import Path
from typing import Any, Callable

import pytest
from nicegui import ui
from nicegui.testing import User

from frontend.webui.i18n_catalogue import render_message, render_message_plain, set_active_messages
from frontend.webui.audit_labels import audit_entity_type_label
from frontend.webui.api_client import ApiError
from frontend.webui.messaging_monitor import messaging_monitor

pytest_plugins = ["nicegui.testing.user_plugin"]
pytestmark = pytest.mark.asyncio


def application_audit_callback(namespace):
    tree = ast.parse((Path(__file__).parents[2] / "app.py").read_text())
    guard = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                 and n.name == "guarded_page_navigation")
    audit_page = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "select_audit_trail")
    exec(compile(ast.Module(body=[guard, audit_page], type_ignores=[]), "app.py", "exec"), namespace)
    monitor = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Name) and n.func.id == "messaging_monitor")
    callback = next(k.value for k in monitor.keywords if k.arg == "open_audit")
    return eval(compile(ast.Expression(callback), "app.py", "eval"), namespace)


@pytest.mark.parametrize("tag", ["en", "ar"])
@pytest.mark.parametrize("authorized,can_leave", [(True, True), (True, False), (False, True)])
async def test_monitor_audit_button_routes_to_dedicated_page_with_navigation_guard(
    user: User, tag, authorized, can_leave,
):
    events = []
    searches = []
    translations = {
        r["message_key"]: r["translated_text"]
        for r in json.loads((Path(__file__).parents[2] / "i18n/messages.ar.generated.json").read_text())["items"]
    } if tag == "ar" else {}
    button_text = translations.get("messaging.monitor.audit") or render_message_plain("messaging.monitor.audit")
    title_key = "webui.select_audit_trail.text.audit_trail_2f72156b"
    title_text = translations.get(title_key) or render_message_plain(title_key)

    class Api:
        def cancel_pending_reads(self):
            events.append("cancel")

        async def request(self, method, path, **kwargs):
            if path.endswith(("/gateways", "/producers")):
                return {"items": [], "next_cursor": None}
            return {"alerts": [], "metrics": [], "retention": {}, "can_view_audit": authorized}

        async def event_history_filter_options(self):
            # No notification events yet: the shortcut must stay scoped anyway.
            return {"entity_types": ["record"], "operations": [], "sources": [], "actor_types": []}

        async def search_request(self, resource, payload):
            assert resource == "event-history"
            searches.append(payload)
            return {"items": [{"id": 1, "entity_type": "system_notification"}], "total": 75}

    @ui.page("/monitor-audit-navigation")
    async def page():
        set_active_messages(translations)
        host = ui.column()
        api = Api()

        async def discard_guard(reason):
            assert reason == "leave this page"
            return can_leave

        namespace = {
            "state": {"discard_navigation_guard": discard_guard}, "api": api,
            "inspect": inspect, "Callable": Callable, "Any": Any,
            "ui": ui, "render_message": render_message,
            "audit_entity_type_label": audit_entity_type_label,
            "register_navigation": lambda *args: events.append("audit"),
            "show_authenticated_view": lambda: None,
            "title": ui.label(), "subtitle": ui.label(), "guidance": ui.label(),
            "add_button": ui.button(), "add_record_button": ui.button(),
            "search_bar": ui.row(), "aggregation_mode_bar": ui.row(),
            "table_container": host, "ApiError": ApiError,
            "hydrate_historical_audit_identities": lambda rows: None,
            "render_event_timeline": lambda rows, container: None,
            "set_connection_status": lambda connected: None,
            "event_label": str,
        }
        callback = application_audit_callback(namespace)
        ui.button("Sidebar audit fixture", on_click=lambda: namespace["guarded_page_navigation"](
            namespace["select_audit_trail"]
        )).mark("sidebar-audit")
        await messaging_monitor(api=api, container=host, active=lambda:True,
                                format_timestamp=str, open_audit=callback)

    await user.open("/monitor-audit-navigation")
    if not authorized:
        await user.should_not_see(button_text)
        assert events == []
        return
    user.find(button_text).click()
    if can_leave:
        await user.should_see(title_text)
        assert events == ["cancel", "audit"]
        assert searches[0]["where"] == {
            "field": "entity_type", "operator": "eq", "value": "system_notification",
        }
        assert searches[0]["limit"] == 50 and searches[0]["offset"] == 0
        assert any(control.value == "system_notification" for control in user.find(kind=ui.select).elements)
        await user.should_not_see(button_text)
        next_key = "webui.select_audit_trail.button.next_4982f418"
        user.find(translations.get(next_key) or render_message_plain(next_key)).click()
        await user.should_see("51")
        assert searches[-1]["offset"] == 50
        assert searches[-1]["where"] == searches[0]["where"]
        user.find(marker="sidebar-audit").click()
        await user.should_not_see("51")
        assert "where" not in searches[-1]
        assert searches[-1]["offset"] == 0
    else:
        await user.should_see(button_text)
        assert events == []
