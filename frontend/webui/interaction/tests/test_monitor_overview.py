"""At-a-glance monitor contracts with fixture API responses only."""

import asyncio
import ast
import json
from pathlib import Path

import pytest
from nicegui import ui
from nicegui.testing import User

from frontend.webui.api_client import ApiError
from frontend.webui.i18n_catalogue import set_active_messages, render_message_plain, strip_diagnostic_metadata, load_english_manifest
from frontend.webui.messaging_monitor import messaging_monitor, OPERATIONAL_COUNTERS

pytest_plugins = ["nicegui.testing.user_plugin"]
pytestmark = pytest.mark.asyncio


def messages(tag):
    return {r["message_key"]: r["translated_text"] for r in json.loads(
        (Path(__file__).parents[2] / "i18n/messages.ar.generated.json").read_text()
    )["items"]} if tag == "ar" else {}


@pytest.mark.parametrize("tag", ["en", "ar"])
async def test_monitor_complete_summary_paging_refresh_and_disclosure(user: User, tag):
    translated = messages(tag)
    calls = []
    recovering = False
    entered = asyncio.Event()
    release = asyncio.Event()
    block = False

    def text(name):
        key = "messaging.monitor." + name
        return translated.get(key) or render_message_plain(key)

    def gateway(identity):
        return dict(instance_id=identity, host_addresses=["10.0.0.1"], api_port=8000,
                    observed_at="2026-10-05T13:34:00+04:00", listener_connected=True,
                    health_status="connected", active_connections=2, notifications_received=10,
                    listener_generation=1, slow_disconnects=0, last_notification_at=None)

    class Api:
        async def request(self, method, path, **kwargs):
            calls.append((path, kwargs))
            if block:
                entered.set()
                await release.wait()
            if path.endswith("/gateways"):
                after = kwargs.get("params", {}).get("after")
                return {"items": [gateway("second-page" if after else "first-page")],
                        "next_cursor": None if after else "gateway-cursor"}
            if path.endswith("/producers"):
                after = kwargs.get("params", {}).get("after")
                return {"items": [dict(producer_code="b" if after else "a", name="Producer B" if after else "Producer A", metric="notifications_emitted", value=200 if after else 100, observations=1)],
                        "next_cursor": None if after else "producer-cursor"}
            return {"gateways": {"instances": 10, "unhealthy": 0 if recovering else 2},
                    "alerts": [] if recovering else [{"metric": "cleanup_failure"}],
                    "retention": {"approaching_expiry": 12, "active_inbox": 80, "restorable_inbox": 20, "active_outbox": 40, "restorable_outbox": 10},
                    "metrics": [{"metric": "cleanup_seconds", "value": 6, "observations": 3}], "can_view_audit": False}

    @ui.page("/monitor-overview-test")
    async def page():
        set_active_messages(translated)
        await messaging_monitor(api=Api(), container=ui.column(), active=lambda: True, format_timestamp=str)

    await user.open("/monitor-overview-test")
    await user.should_see("Producer A")
    assert len(calls) == 3
    ring = next(e for e in user.client.elements.values() if e.tag == "q-circular-progress")
    assert ring.props["max"] == 10 and ring.value == 8  # Not the one loaded row.
    bars = [e for e in user.client.elements.values() if e.tag == "q-linear-progress"]
    assert [b.value for b in bars] == [0.8, 0.8, 1]
    # User fixture does not emulate QExpansionItem's browser v-model toggle.
    next(e for e in user.client.elements.values() if e.tag == "q-expansion-item").open()
    await user.should_see("first-page")
    expansions = [e for e in user.client.elements.values() if e.tag == "q-expansion-item"]
    assert any(e.value for e in expansions)
    # Both bounded collections retain independent cursor requests.
    user.find(kind=ui.button, content=translated.get("messaging.action.next") or render_message_plain("messaging.action.next")).click()
    await user.should_see("Producer B")
    await user.should_see("second-page")
    assert {(p, k['params']['after']) for p, k in calls if k.get('params', {}).get('after')} == {
        ('/api/v1/messages/monitor/gateways', 'gateway-cursor'),
        ('/api/v1/messages/monitor/producers', 'producer-cursor'),
    }
    bars = [e for e in user.client.elements.values() if e.tag == "q-linear-progress"]
    assert [b.value for b in bars] == [0.8, 0.8, 0.5, 1]
    block = True
    recovering = True
    user.find(translated.get("messaging.action.refresh") or render_message_plain("messaging.action.refresh")).click()
    await asyncio.wait_for(entered.wait(), 1)
    await user.should_see("Producer A")
    await user.should_see("Producer B")  # Existing snapshot survives loading.
    assert len(calls) == 8  # All three reads start concurrently.
    release.set()
    await user.should_not_see("Producer B")
    ring = next(e for e in user.client.elements.values() if e.tag == "q-circular-progress")
    assert ring.value == 10
    assert any(e.value for e in user.client.elements.values() if e.tag == "q-expansion-item")
    await user.open("/monitor-overview-test")
    assert len(calls) == 11


async def test_monitor_failed_refresh_keeps_snapshot_and_zero_has_no_ring(user: User):
    failed = False

    class Api:
        async def request(self, method, path, **kwargs):
            if failed:
                raise ApiError(503, "unavailable")
            if path.endswith(("/gateways", "/producers")):
                return {"items": [], "next_cursor": None}
            return {"gateways": {"instances": 0, "unhealthy": 0}, "alerts": [],
                    "retention": {"approaching_expiry": 77}, "metrics": [], "can_view_audit": False}

    @ui.page("/monitor-refresh-failure")
    async def page():
        set_active_messages({})
        await messaging_monitor(api=Api(), container=ui.column(), active=lambda: True, format_timestamp=str)

    await user.open("/monitor-refresh-failure")
    await user.should_see("77")
    assert not any(e.tag == "q-circular-progress" for e in user.client.elements.values())
    failed = True
    user.find("Refresh").click()
    await user.should_see(render_message_plain("messaging.error.failed"))
    await user.should_see("77")
    assert next(iter(user.find(kind=ui.button, content="Refresh").elements)).enabled


@pytest.mark.parametrize("tag", ["en", "ar"])
async def test_every_operational_counter_has_localized_muted_subtitle(user: User, tag):
    translated = messages(tag)
    # Read the source contract without importing backend/database fixtures.
    operations = Path(__file__).parents[4] / "backend/services/api/messaging/operations.py"
    tree = ast.parse(operations.read_text())
    names = next(n.value.args[0] for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "METRICS" for t in n.targets))
    assert set(ast.literal_eval(names)) == OPERATIONAL_COUNTERS
    metrics = [dict(metric=name, value=100, observations=10) for name in sorted(OPERATIONAL_COUNTERS)]

    class Api:
        async def request(self, method, path, **kwargs):
            if path.endswith("/gateways"):
                return {"items": [], "next_cursor": None}
            if path.endswith("/producers"):
                return {"items": [dict(row, producer_code="sample", name="Sample producer", unresolved_since=None) for row in metrics], "next_cursor": None}
            return {"gateways": {"instances": 0, "unhealthy": 0}, "metrics": metrics,
                    "alerts": [], "retention": {}, "can_view_audit": False}

    @ui.page("/monitor-subtitles")
    async def page():
        set_active_messages(translated)
        await messaging_monitor(api=Api(), container=ui.column(), active=lambda: True, format_timestamp=str)

    await user.open("/monitor-subtitles")
    await user.should_see("Sample producer")
    for name in OPERATIONAL_COUNTERS:
        key = "messaging.monitor.description." + name
        expected = translated.get(key) or load_english_manifest()[key]["default_text"]
        labels = [e for e in user.client.elements.values() if isinstance(e, ui.label)
                  and strip_diagnostic_metadata(e.text) == expected]
        assert len(labels) >= 2  # Complete operational and producer diagnostics.
        assert all("text-slate-500" in e.classes for e in labels)
