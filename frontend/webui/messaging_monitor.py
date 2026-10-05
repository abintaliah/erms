"""Bounded, privilege-gated operational overview with progressive diagnostics."""

import asyncio
from collections import defaultdict

from nicegui import ui

from .api_client import ApiError
from .i18n_catalogue import render_message


OPERATIONAL_COUNTERS = frozenset((
    "send_success",
    "send_failure",
    "fanout_count",
    "notifications_emitted",
    "catchup_failure",
    "restricted_count",
    "capture_failure",
    "capture_seconds",
    "cleanup_failure",
    "cleanup_seconds",
    "purged_messages",
    "purged_groups",
    "purged_drafts",
    "group_size",
    "delayed_groups",
    "system_failure",
    "system_seconds",
    "test_success",
    "test_failure",
    "test_rate_rejected",
    "test_seconds",
))


def metric_value(row):
    value = row["value"]
    if row["metric"].endswith("_seconds"):
        value /= max(row["observations"], 1)
    return round(value, 3)


async def messaging_monitor(*, api, container, active, format_timestamp, open_audit=None):
    # Disclosure state belongs to this page only; no operational data is cached.
    disclosures = {}
    revision = 0

    def text(name, **params):
        key = "messaging.monitor." + name
        return render_message(key, **params)

    def number(value):
        return f"{value:,}" if isinstance(value, int) else str(value)

    def panel(name):
        card = ui.card().classes("erms-card w-full p-0 shadow-none border border-blue-100")
        with card:
            ui.label(text(name)).classes("w-full bg-blue-50 text-blue-900 font-semibold px-4 py-3")
        return card

    def disclosure(name, identity):
        return ui.expansion(
            text(name), value=disclosures.get(identity, False),
            on_value_change=lambda e: disclosures.__setitem__(identity, e.value),
        ).classes("w-full text-blue-800")

    def status_badge(name, healthy=False):
        with ui.row().classes(
            "items-center gap-1 rounded px-2 py-1 "
            + ("bg-green-50 text-green-800" if healthy else "bg-amber-50 text-amber-900")
        ):
            ui.icon("check_circle" if healthy else "warning", size="xs")
            ui.label(text(name)).classes("text-xs font-semibold")

    def fact(name, value, large=False):
        with ui.column().classes("gap-1 min-w-0 max-w-xs"):
            ui.label(number(value)).classes("font-semibold tabular-nums " + ("text-3xl" if large else "text-xl"))
            ui.label(text(name)).classes("text-xs text-slate-600")
            if name in OPERATIONAL_COUNTERS:
                ui.label(text("description." + name)).classes("text-xs text-slate-500")

    def pair(name, value, *, describe=False):
        with ui.column().classes("w-full gap-1"):
            with ui.row().classes("w-full items-start justify-between gap-2 flex-nowrap"):
                ui.label(text(name)).classes("text-sm min-w-0")
                ui.label(
                    format_timestamp(value) if name.startswith("oldest") and value else number(value or 0)
                ).classes("text-sm font-semibold tabular-nums shrink-0").props('dir="auto"')
            if describe:
                ui.label(text("description." + name)).classes("text-xs text-slate-500")

    with container:
        # Reuse the messaging workspace's established native RTL row treatment.
        with ui.column().classes("messaging-workspace w-full gap-3 p-3"):
            with ui.row().classes("w-full items-center justify-between"):
                status = ui.label("").classes("text-sm text-slate-600").props('role="status"')
                refresh = ui.button(render_message("messaging.action.refresh"), icon="refresh", on_click=lambda: load()).props("outline no-caps")
            host = ui.column().classes("w-full gap-4")

    async def load():
        nonlocal revision
        if not active():
            return
        revision += 1
        current = revision
        refresh.disable()
        refresh.props("loading")
        with host:
            status.set_text(render_message("messaging.state.loading"))
        try:
            data, gateway_page, producer_page = await asyncio.gather(
                api.request("GET", "/api/v1/messages/monitor"),
                api.request("GET", "/api/v1/messages/monitor/gateways", params={"limit": 25}),
                api.request("GET", "/api/v1/messages/monitor/producers", params={"limit": 25}),
            )
        except asyncio.CancelledError:
            return
        except ApiError:
            if active() and revision == current:
                with host:
                    status.set_text(render_message("messaging.error.failed"))
            return
        finally:
            if active() and revision == current:
                refresh.enable()
                refresh.props(remove="loading")
        if not active() or revision != current:
            return
        status.set_text("")
        # Retain the usable snapshot until every independent read has succeeded.
        host.clear()
        with host:
            counts = data.get("gateways") or {
                "instances": len(gateway_page["items"]),
                "unhealthy": sum(r.get("health_status", "connected" if r["listener_connected"] else "disconnected") != "connected" for r in gateway_page["items"]),
            }
            total, unhealthy = counts["instances"], counts["unhealthy"]
            connected = total - unhealthy
            attention = unhealthy + len(data["alerts"])
            retention = data["retention"]
            metrics = {r["metric"]: r for r in data["metrics"]}
            with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-3 gap-3"):
                with ui.card().classes("erms-card w-full shadow-none border " + ("border-amber-200 bg-amber-50" if attention else "border-green-100 bg-green-50")):
                    ui.label(text("requires_attention")).classes("text-sm text-slate-600")
                    ui.label(number(attention)).classes("text-3xl font-semibold tabular-nums")
                    ui.label(text("attention_breakdown", gateways=unhealthy, operations=len(data["alerts"]))).classes("text-xs text-slate-600")
                with ui.card().classes("erms-card w-full shadow-none border border-blue-100"):
                    ui.label(text("connected_gateways")).classes("text-sm text-slate-600")
                    ui.label(text("connected_total", connected=connected, total=total)).classes("text-3xl font-semibold tabular-nums").props('dir="ltr"')
                    ui.label(text("freshness")).classes("text-xs text-slate-600")
                with ui.card().classes("erms-card w-full shadow-none border border-blue-100"):
                    ui.label(text("approaching_expiry")).classes("text-sm text-slate-600")
                    ui.label(number(retention.get("approaching_expiry", 0))).classes("text-3xl font-semibold tabular-nums")
                    ui.label(text("expiry_window")).classes("text-xs text-slate-600")
            if attention:
                with ui.row().classes("w-full items-start flex-nowrap rounded-lg border border-amber-200 bg-amber-50 p-3 gap-3"):
                    ui.icon("warning", color="warning")
                    with ui.column().classes("gap-1 min-w-0"):
                        ui.label(text("attention_guidance")).classes("font-semibold text-amber-900")
                        for alert in data["alerts"]:
                            ui.label(text("alert") + ": " + text(alert["metric"])).classes("text-sm text-amber-900")
            with ui.grid().classes("w-full grid-cols-1 lg:grid-cols-12 gap-4 items-start"):
                with ui.column().classes("w-full min-w-0 lg:col-span-7 gap-4"):
                    gateway_host = panel("gateways")

                    def gateways(page):
                        with gateway_host:
                            if not page["items"]:
                                ui.label(render_message("messaging.state.empty")).classes("p-4 text-slate-600")
                            for row in page["items"]:
                                health_status = row.get("health_status", "connected" if row["listener_connected"] else "disconnected")
                                with ui.column().classes("w-full border-b border-slate-200 px-4 py-3 gap-2"):
                                    with ui.row().classes("w-full items-center justify-between gap-2"):
                                        addresses, port = row.get("host_addresses") or [], row.get("api_port")
                                        if addresses and port:
                                            endpoints = ", ".join(f"[{a}]:{port}" if ":" in a else f"{a}:{port}" for a in addresses)
                                            ui.label(text("gateway_endpoint", endpoints=endpoints)).classes("font-semibold break-all min-w-0").props('dir="ltr"')
                                        else:
                                            ui.label(text("endpoint_unavailable")).classes("font-semibold")
                                        status_badge({"connected": "connected", "disconnected": "disconnected", "overdue": "overdue"}[health_status], health_status == "connected")
                                    ui.label(text("last_report", timestamp=format_timestamp(row["observed_at"]))).classes("text-xs text-slate-600")
                                    if len(addresses) > 1:
                                        ui.label(text("address_ambiguous")).classes("text-xs text-slate-600")
                                    if health_status == "overdue":
                                        ui.label(text("last_reported_values")).classes("text-xs text-amber-900")
                                    with ui.row().classes("gap-6"):
                                        fact("active_connections", row["active_connections"])
                                        fact("notifications_received", row["notifications_received"])
                                    with disclosure("instance_diagnostics", "gateway:" + str(row["instance_id"])):
                                        ui.label(text("instance_id", instance_id=str(row["instance_id"]))).classes("text-xs break-all")
                                        for name in ("listener_generation", "slow_disconnects", "last_notification_at"):
                                            ui.label(text(name) + ": " + (format_timestamp(row[name]) if name == "last_notification_at" and row[name] else str(row[name] or 0))).classes("text-sm")
                            if page.get("next_cursor"):
                                async def more():
                                    button.disable()
                                    try:
                                        next_page = await api.request("GET", "/api/v1/messages/monitor/gateways", params={"after": page["next_cursor"], "limit": 25})
                                    except asyncio.CancelledError:
                                        return
                                    except ApiError:
                                        if active() and revision == current:
                                            with host:
                                                button.enable()
                                                status.set_text(render_message("messaging.error.failed"))
                                        return
                                    if active() and revision == current:
                                        button.delete()
                                        gateways(next_page)
                                button = ui.button(render_message("messaging.action.next"), on_click=more).props("outline no-caps").classes("m-3")
                    gateways(gateway_page)
                    with panel("metrics"):
                        with ui.column().classes("w-full p-4 gap-3"):
                            ui.label(text("cumulative")).classes("text-xs text-slate-600")
                            if not metrics:
                                ui.label(render_message("messaging.state.empty"))
                            else:
                                with ui.row().classes("gap-6"):
                                    for name in ("send_success", "send_failure", "purged_messages", "cleanup_seconds"):
                                        if name in metrics:
                                            fact(name, metric_value(metrics[name]))
                                with disclosure("all_counters", "metrics"):
                                    for row in data["metrics"]:
                                        pair(row["metric"], metric_value(row), describe=True)
                with ui.column().classes("w-full min-w-0 lg:col-span-5 gap-4"):
                    with panel("gateway_health"):
                        with ui.row().classes("w-full p-4 items-center gap-5"):
                            if total:
                                label = text("connected_total", connected=connected, total=total)
                                with ui.circular_progress(connected, max=total, size="100px", show_value=False, color="positive").props(f'track-color={"amber-3" if unhealthy else "grey-3"}') as ring:
                                    ui.label(label).classes("font-semibold text-lg text-slate-800").props('dir="ltr"')
                                ring.props["aria-label"] = text("connected_gateways") + ": " + label
                                with ui.column().classes("gap-2"):
                                    status_badge("connected", True)
                                    ui.label(number(connected)).classes("font-semibold tabular-nums")
                                    if unhealthy:
                                        status_badge("requires_attention")
                                        ui.label(number(unhealthy)).classes("font-semibold tabular-nums")
                            else:
                                ui.label(render_message("messaging.state.empty"))
                            ui.label(text("freshness")).classes("w-full text-xs text-slate-600")
                    with panel("retention"):
                        with ui.column().classes("w-full p-4 gap-3"):
                            for kind in ("inbox", "outbox"):
                                active_count = retention.get("active_" + kind, 0) or 0
                                restorable = retention.get("restorable_" + kind, 0) or 0
                                entry_total = active_count + restorable
                                with ui.column().classes("w-full gap-1"):
                                    with ui.row().classes("w-full justify-between"):
                                        ui.label(text(kind + "_entries")).classes("font-semibold text-sm")
                                        ui.label(number(entry_total)).classes("font-semibold tabular-nums")
                                    if entry_total:
                                        bar = ui.linear_progress(active_count / entry_total, show_value=False, size="8px", color="primary").props("rounded track-color=amber-4")
                                        bar.props["aria-label"] = text("active_" + kind) + ": " + str(active_count) + "; " + text("restorable_" + kind) + ": " + str(restorable)
                                    with ui.row().classes("w-full justify-between gap-2"):
                                        ui.label(text("active_" + kind) + ": " + number(active_count)).classes("text-xs text-slate-600")
                                        ui.label(text("restorable_" + kind) + ": " + number(restorable)).classes("text-xs text-slate-600")
                            for name in ("expired_retained", "eligible_groups", "oldest_eligible_group"):
                                if name in retention:
                                    pair(name, retention[name])
                            with disclosure("more_retention", "retention"):
                                for name, value in retention.items():
                                    pair(name, value)
                    producer_host = panel("producers")
                    producer_rows = []
                    with producer_host:
                        ui.label(text("producer_scope")).classes("text-xs text-slate-600 px-4 pt-3")
                        producer_content = ui.column().classes("w-full gap-0")
                        producer_more = ui.row().classes("px-4 pb-3")

                    def producers(page):
                        producer_rows.extend(page["items"])
                        grouped = defaultdict(list)
                        for row in producer_rows:
                            grouped[row["producer_code"]].append(row)
                        scale = max((r["value"] for r in producer_rows if r["metric"] == "notifications_emitted"), default=0)
                        producer_content.clear()
                        producer_more.clear()
                        with producer_content:
                            if not grouped:
                                ui.label(render_message("messaging.state.empty")).classes("p-4 text-slate-600")
                            for code, rows in grouped.items():
                                with ui.column().classes("w-full px-4 py-3 gap-2 border-b border-slate-200"):
                                    ui.label((rows[0].get("localized") or {}).get("name") or rows[0].get("name") or code).classes("font-semibold text-sm break-words")
                                    emitted = next((r for r in rows if r["metric"] == "notifications_emitted"), None)
                                    if emitted:
                                        ui.label(text("notifications_emitted") + ": " + number(emitted["value"])).classes("text-sm tabular-nums")
                                        ui.label(text("description.notifications_emitted")).classes("text-xs text-slate-500")
                                        if scale:
                                            bar = ui.linear_progress(emitted["value"] / scale, show_value=False, size="8px").props("rounded")
                                            bar.props["aria-label"] = text("notifications_emitted") + ": " + str(emitted["value"])
                                    for row in rows:
                                        if row.get("unresolved_since"):
                                            with ui.row().classes("items-center gap-1 text-amber-900"):
                                                ui.icon("warning", size="xs")
                                                ui.label(text(row["metric"]) + ": " + number(metric_value(row))).classes("text-sm font-semibold")
                                            ui.label(text("description." + row["metric"])).classes("text-xs text-slate-500")
                                    with disclosure("producer_diagnostics", "producer:" + code):
                                        for row in rows:
                                            pair(row["metric"], metric_value(row), describe=True)
                        if page.get("next_cursor"):
                            with producer_more:
                                async def more():
                                    button.disable()
                                    try:
                                        next_page = await api.request("GET", "/api/v1/messages/monitor/producers", params={"after": page["next_cursor"], "limit": 25})
                                    except asyncio.CancelledError:
                                        return
                                    except ApiError:
                                        if active() and revision == current:
                                            with host:
                                                button.enable()
                                                status.set_text(render_message("messaging.error.failed"))
                                        return
                                    if active() and revision == current:
                                        producers(next_page)
                                button = ui.button(render_message("messaging.action.next"), on_click=more).props("outline no-caps")
                    producers(producer_page)
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(text("privacy")).classes("text-xs text-slate-600")
                if data["can_view_audit"] and open_audit:
                    ui.button(text("audit"), icon="history", on_click=open_audit).props("flat no-caps")

    await load()


MESSAGING_MESSAGE_KEYS = (
    "messaging.monitor.description.capture_failure",
    "messaging.monitor.description.capture_seconds",
    "messaging.monitor.description.catchup_failure",
    "messaging.monitor.description.cleanup_failure",
    "messaging.monitor.description.cleanup_seconds",
    "messaging.monitor.description.delayed_groups",
    "messaging.monitor.description.fanout_count",
    "messaging.monitor.description.group_size",
    "messaging.monitor.description.notifications_emitted",
    "messaging.monitor.description.purged_drafts",
    "messaging.monitor.description.purged_groups",
    "messaging.monitor.description.purged_messages",
    "messaging.monitor.description.restricted_count",
    "messaging.monitor.description.send_failure",
    "messaging.monitor.description.send_success",
    "messaging.monitor.description.system_failure",
    "messaging.monitor.description.system_seconds",
    "messaging.monitor.description.test_failure",
    "messaging.monitor.description.test_rate_rejected",
    "messaging.monitor.description.test_seconds",
    "messaging.monitor.description.test_success",

    "messaging.monitor.all_counters",
    "messaging.monitor.attention_breakdown",
    "messaging.monitor.attention_guidance",
    "messaging.monitor.connected_gateways",
    "messaging.monitor.connected_total",
    "messaging.monitor.cumulative",
    "messaging.monitor.expiry_window",
    "messaging.monitor.freshness",
    "messaging.monitor.gateway_health",
    "messaging.monitor.inbox_entries",
    "messaging.monitor.instance_diagnostics",
    "messaging.monitor.last_reported_values",
    "messaging.monitor.more_retention",
    "messaging.monitor.outbox_entries",
    "messaging.monitor.producer_diagnostics",
    "messaging.monitor.producer_scope",
    "messaging.monitor.requires_attention",

    "messaging.monitor.title",
    "messaging.monitor.privacy",
    "messaging.monitor.alert",
    "messaging.monitor.retention",
    "messaging.monitor.metrics",
    "messaging.monitor.gateways",
    "messaging.monitor.connected",
    "messaging.monitor.disconnected",
    "messaging.monitor.overdue",
    "messaging.monitor.gateway_endpoint",
    "messaging.monitor.endpoint_unavailable",
    "messaging.monitor.address_ambiguous",
    "messaging.monitor.instance_id",
    "messaging.monitor.last_report",
    "messaging.monitor.active_connections",
    "messaging.monitor.notifications_received",
    "messaging.monitor.audit",
    "messaging.monitor.approaching_expiry",
    "messaging.monitor.expired_retained",
    "messaging.monitor.oldest_expired_candidate",
    "messaging.monitor.active_inbox",
    "messaging.monitor.restorable_inbox",
    "messaging.monitor.send_success",
    "messaging.monitor.send_failure",
    "messaging.monitor.fanout_count",
    "messaging.monitor.notifications_emitted",
    "messaging.monitor.catchup_failure",
    "messaging.monitor.restricted_count",
    "messaging.monitor.capture_failure",
    "messaging.monitor.capture_seconds",
    "messaging.monitor.cleanup_failure",
    "messaging.monitor.cleanup_seconds",
    "messaging.monitor.purged_messages",
    "messaging.monitor.purged_groups",
    "messaging.monitor.purged_drafts",
    "messaging.monitor.group_size",
    "messaging.monitor.delayed_groups",
    "messaging.monitor.system_failure",
    "messaging.monitor.system_seconds",
    "messaging.monitor.test_success",
    "messaging.monitor.test_failure",
    "messaging.monitor.test_rate_rejected",
    "messaging.monitor.test_seconds",
    "messaging.monitor.group_members",
    "messaging.monitor.expired_retained_by_group",
    "messaging.monitor.eligible_groups",
    "messaging.monitor.oldest_eligible_group",
    "messaging.monitor.largest_group",
    "messaging.monitor.group_failures",
    "messaging.monitor.active_outbox",
    "messaging.monitor.restorable_outbox",
    "messaging.monitor.listener_generation",
    "messaging.monitor.slow_disconnects",
    "messaging.monitor.last_notification_at",
    "messaging.monitor.producers",
)
