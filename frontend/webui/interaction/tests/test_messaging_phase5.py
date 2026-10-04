"""Retention and operations UI contracts without database access."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from nicegui import ui
from nicegui.testing import User
from frontend.webui.messaging_workspace import messaging_workspace
from frontend.webui.messaging_monitor import messaging_monitor
from frontend.webui.app import relationship_select
from frontend.webui.i18n_catalogue import set_active_messages, render_message_plain

pytest_plugins = ["nicegui.testing.user_plugin"]
pytestmark = pytest.mark.asyncio


def language(tag):
    set_active_messages(
        {
            r["message_key"]: r["translated_text"]
            for r in json.loads(
                (
                    Path(__file__).parents[2] / "i18n/messages.ar.generated.json"
                ).read_text()
            )["items"]
        }
        if tag == "ar"
        else {}
    )


@pytest.mark.parametrize("tag", ["en", "ar"])
async def test_deleted_mailbox_restore_uses_own_route_and_refresh(user: User, tag):
    calls = []
    restored = False
    message = dict(
        id="delivery",
        envelope_id="envelope",
        availability="available",
        sender_name="system",
        sender_kind="system",
        message_kind="system_notification",
        subject="Test notice",
        body_rich_text="<p>Notice</p>",
        sent_at="2026-01-01T00:00:00Z",
        expires_at="2026-02-01T00:00:00Z",
        restorable_until="2099-03-01T00:00:00Z",
        is_test=True,
        is_read=False,
        priority="normal",
        security_level_id=1,
        security_level_name="General",
        action_required=False,
        selectors=[],
        resource_links=[],
        can_delete=True,
    )

    class Api:
        async def request(self, method, path, **kwargs):
            nonlocal restored
            calls.append((method, path, kwargs))
            if path.endswith("/restore"):
                restored = True
                return {}
            if path.endswith("/delivery"):
                return message
            return {
                "items": (
                    [] if restored or "/recently-deleted/" not in path else [message]
                ),
                "has_more": False,
            }

    @ui.page("/retention-test")
    async def page():
        language(tag)
        await messaging_workspace(
            api=Api(),
            container=ui.column(),
            mailbox="inbox",
            can_exchange=False,
            relationship_select=relationship_select,
            bind_relationship=lambda *a, **k: None,
            open_resource=AsyncMock(),
            format_timestamp=str,
            active=lambda: True,
        )

    await user.open("/retention-test")
    language(tag)
    user.find(render_message_plain("messaging.retention.recently_deleted")).click()
    await user.should_see("Test notice")
    user.find(render_message_plain("messaging.action.open")).click()
    await user.should_see(render_message_plain("messaging.retention.restore"))
    user.find(render_message_plain("messaging.retention.restore")).click()
    await user.should_see(render_message_plain("messaging.state.empty"))
    assert ("POST", "/api/v1/messages/inbox/delivery/restore") in [
        (m, p) for m, p, _ in calls
    ]
    assert all(k.get("params", {}).get("limit", 25) <= 25 for _, _, k in calls)


async def test_monitor_abandonment_and_bounded_requests(user: User):
    calls = []
    alive = True
    block = asyncio.Event()

    class Api:
        async def request(self, method, path, **kwargs):
            calls.append((path, kwargs))
            await block.wait()
            if path.endswith(("/gateways", "/producers")):
                return {"items": []}
            return {
                "alerts": [],
                "metrics": [],
                "retention": {"approaching_expiry": 0},
                "can_view_audit": False,
            }

    @ui.page("/monitor-test")
    async def page():
        language("en")
        host = ui.column()
        ui.timer(
            0.01,
            lambda: messaging_monitor(
                api=Api(), container=host, active=lambda: alive, format_timestamp=str
            ),
            once=True,
        )

    await user.open("/monitor-test")
    await user.should_see(render_message_plain("messaging.state.loading"))
    alive = False
    block.set()
    await asyncio.sleep(0.05)
    assert len(calls) == 3 and calls[1][1]["params"]["limit"] == 25
    await user.should_not_see(render_message_plain("messaging.monitor.privacy"))


async def test_capture_button_is_busy_until_staging_finishes(user: User):
    entered = asyncio.Event()
    release = asyncio.Event()
    captures = []
    message = dict(
        id="delivery",
        envelope_id="envelope",
        availability="available",
        sender_name="Sender",
        sender_kind="user",
        message_kind="user_message",
        subject="Capture this message",
        body_rich_text="<p>Preserve this body</p>",
        sent_at="2026-01-01T00:00:00Z",
        expires_at="2029-01-01T00:00:00Z",
        is_test=False,
        is_read=True,
        priority="normal",
        security_level_id=1,
        security_level_name="General",
        action_required=False,
        selectors=[],
        resource_links=[],
        can_delete=False,
    )

    class Api:
        async def request(self, method, path, **kwargs):
            if path.endswith("/read"):
                return message
            return {"items": [message], "has_more": False}

    async def capture(identity, root):
        captures.append((identity, root))
        entered.set()
        await release.wait()

    @ui.page("/capture-busy")
    async def page():
        language("en")
        await messaging_workspace(
            api=Api(),
            container=ui.column(),
            mailbox="inbox",
            can_exchange=False,
            relationship_select=relationship_select,
            bind_relationship=lambda *a, **k: None,
            open_resource=AsyncMock(),
            format_timestamp=str,
            active=lambda: True,
            capture_record=capture,
        )

    await user.open("/capture-busy")
    user.find("Open").click()
    await user.should_see("Save as record")
    user.find("Save as record").click()
    await asyncio.wait_for(entered.wait(), 1)
    button = next(iter(user.find("Save as record").elements))
    assert not button.enabled and button.props["loading"]
    release.set()
    await asyncio.sleep(0.05)
    assert button.enabled and "loading" not in button.props
    assert captures == [("envelope", None)]
