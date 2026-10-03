"""Sanitized operations overview; navigation and every read remain privilege gated."""

import asyncio
from nicegui import ui
from .api_client import ApiError
from .i18n_catalogue import render_message


async def messaging_monitor(
    *, api, container, active, format_timestamp, open_audit=None
):
    def metric_text(name):
        key = "messaging.monitor." + name
        return render_message(key)

    revision = 0
    with container:
        with ui.column().classes("w-full gap-3 p-3"):
            status = ui.label("")
            ui.button(
                render_message("messaging.action.refresh"),
                icon="refresh",
                on_click=lambda: load(),
            ).props("flat no-caps")
            host = ui.column().classes("w-full gap-3")

    async def load():
        nonlocal revision
        revision += 1
        current = revision
        status.set_text(render_message("messaging.state.loading"))
        try:
            data, gateway_page, producer_page = await asyncio.gather(
                api.request("GET", "/api/v1/messages/monitor"),
                api.request(
                    "GET", "/api/v1/messages/monitor/gateways", params={"limit": 25}
                ),
                api.request(
                    "GET", "/api/v1/messages/monitor/producers", params={"limit": 25}
                ),
            )
        except asyncio.CancelledError:
            return
        except ApiError:
            if active() and revision == current:
                status.set_text(render_message("messaging.error.failed"))
            return
        if not active() or revision != current:
            return
        status.set_text("")
        host.clear()
        with host:
            ui.label(render_message("messaging.monitor.privacy")).classes(
                "text-sm text-slate-600"
            )
            for alert in data["alerts"]:
                ui.label(
                    render_message("messaging.monitor.alert")
                    + ": "
                    + (
                        metric_text(alert["metric"])
                        if alert.get("metric")
                        else render_message("messaging.monitor.disconnected")
                    )
                ).classes("text-amber-900 font-semibold")
            with ui.card().classes("w-full shadow-none border border-blue-100"):
                ui.label(render_message("messaging.monitor.retention")).classes(
                    "w-full bg-blue-50 text-blue-900 font-semibold p-3"
                )
                for name, value in data["retention"].items():
                    ui.label(
                        metric_text(name)
                        + ": "
                        + (
                            format_timestamp(value)
                            if name.startswith("oldest") and value
                            else str(value or 0)
                        )
                    )
            with ui.card().classes("w-full shadow-none border border-blue-100"):
                ui.label(render_message("messaging.monitor.metrics")).classes(
                    "w-full bg-blue-50 text-blue-900 font-semibold p-3"
                )
                if not data["metrics"]:
                    ui.label(render_message("messaging.state.empty"))
                for row in data["metrics"]:
                    ui.label(
                        metric_text(row["metric"])
                        + ": "
                        + str(
                            round(
                                (
                                    row["value"] / max(row["observations"], 1)
                                    if row["metric"].endswith("_seconds")
                                    else row["value"]
                                ),
                                3,
                            )
                        )
                    )
            with ui.card().classes(
                "w-full shadow-none border border-blue-100"
            ) as gateway_host:
                ui.label(render_message("messaging.monitor.gateways")).classes(
                    "w-full bg-blue-50 text-blue-900 font-semibold p-3"
                )

            def gateways(page):
                with gateway_host:
                    for row in page["items"]:
                        with ui.column().classes(
                            "w-full border-b border-slate-200 py-2"
                        ):
                            ui.label(str(row["instance_id"])).classes(
                                "text-xs break-all"
                            )
                            ui.label(
                                render_message(
                                    "messaging.monitor.connected"
                                    if row["listener_connected"]
                                    else "messaging.monitor.disconnected"
                                )
                            )
                            ui.label(
                                render_message("messaging.monitor.active_connections")
                                + ": "
                                + str(row["active_connections"])
                            )
                            ui.label(
                                render_message(
                                    "messaging.monitor.notifications_received"
                                )
                                + ": "
                                + str(row["notifications_received"])
                            )
                            for name in (
                                "listener_generation",
                                "slow_disconnects",
                                "last_notification_at",
                            ):
                                ui.label(
                                    metric_text(name)
                                    + ": "
                                    + (
                                        format_timestamp(row[name])
                                        if name == "last_notification_at" and row[name]
                                        else str(row[name] or 0)
                                    )
                                )
                    if page.get("next_cursor"):

                        async def more():
                            button.disable()
                            try:
                                next_page = await api.request(
                                    "GET",
                                    "/api/v1/messages/monitor/gateways",
                                    params={"after": page["next_cursor"], "limit": 25},
                                )
                            except ApiError:
                                if active():
                                    button.enable()
                                    status.set_text(
                                        render_message("messaging.error.failed")
                                    )
                                return
                            if active() and revision == current:
                                button.delete()
                                gateways(next_page)

                        button = ui.button(
                            render_message("messaging.action.next"), on_click=more
                        ).props("outline no-caps")

            gateways(gateway_page)
            with ui.card().classes(
                "w-full shadow-none border border-blue-100"
            ) as producer_host:
                ui.label(render_message("messaging.monitor.producers")).classes(
                    "w-full bg-blue-50 text-blue-900 font-semibold p-3"
                )

            def producers(page):
                with producer_host:
                    if not page["items"]:
                        ui.label(render_message("messaging.state.empty"))
                    for row in page["items"]:
                        ui.label(
                            (
                                (row.get("localized") or {}).get("name")
                                or row.get("name")
                                or row["producer_code"]
                            )
                            + " · "
                            + metric_text(row["metric"])
                            + ": "
                            + str(
                                round(
                                    (
                                        row["value"] / max(row["observations"], 1)
                                        if row["metric"].endswith("_seconds")
                                        else row["value"]
                                    ),
                                    3,
                                )
                            )
                        )
                    if page.get("next_cursor"):

                        async def more():
                            button.disable()
                            try:
                                next_page = await api.request(
                                    "GET",
                                    "/api/v1/messages/monitor/producers",
                                    params={"after": page["next_cursor"], "limit": 25},
                                )
                            except ApiError:
                                if active() and revision == current:
                                    button.enable()
                                    status.set_text(
                                        render_message("messaging.error.failed")
                                    )
                                return
                            if active() and revision == current:
                                button.delete()
                                producers(next_page)

                        button = ui.button(
                            render_message("messaging.action.next"), on_click=more
                        ).props("outline no-caps")

            producers(producer_page)
            if data["can_view_audit"] and open_audit:
                ui.button(
                    render_message("messaging.monitor.audit"), on_click=open_audit
                ).props("flat no-caps")

    await load()


MESSAGING_MESSAGE_KEYS = (
    "messaging.monitor.title",
    "messaging.monitor.privacy",
    "messaging.monitor.alert",
    "messaging.monitor.retention",
    "messaging.monitor.metrics",
    "messaging.monitor.gateways",
    "messaging.monitor.connected",
    "messaging.monitor.disconnected",
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
