"""Database-free EN/AR fixture for the implemented At-a-glance Monitor."""

import asyncio
import ast
import json
from pathlib import Path

from nicegui import ui
from frontend.webui.api_client import ApiError
from frontend.webui.i18n_catalogue import set_active_messages, render_message
from frontend.webui.messaging_monitor import messaging_monitor

ROOT = Path(__file__).resolve().parents[3]
AR = {r['message_key']: r['translated_text'] for r in json.loads(
    (ROOT / 'frontend/webui/i18n/messages.ar.generated.json').read_text()
)['items']}
APP_STYLES = next(n.args[0].value for n in ast.walk(ast.parse(
    (ROOT / 'frontend/webui/app.py').read_text()
)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'add_css' and n.args
                 and isinstance(n.args[0], ast.Constant)
                 and isinstance(n.args[0].value, str) and '.erms-card {' in n.args[0].value)


class FixtureApi:
    def __init__(self, tag):
        self.tag = tag
        self.recovered = False
        self.empty = False
        self.fail = False
        self.calls = 0

    async def request(self, method, path, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.25)
        if self.fail:
            raise ApiError(503, 'fixture failure')
        if path.endswith('/gateways'):
            rows = []
            for index, (connections, hints) in enumerate([(24, 1842), (18, 1260), (0, 856)], 1):
                rows.append(dict(instance_id=f'a8e01fa5-aa84-4062-9661-7f941e01939{index}',
                                 host_addresses=[f'10.20.0.{10+index}'], api_port=8000,
                                 observed_at='05 Oct 2026 · 13:34' if index < 3 else '05 Oct 2026 · 13:31',
                                 listener_connected=True,
                                 health_status='connected' if index < 3 or self.recovered else 'overdue',
                                 active_connections=connections, notifications_received=hints,
                                 listener_generation=1, slow_disconnects=0,
                                 last_notification_at='05 Oct 2026 · 13:34'))
            return {'items': [] if self.empty else rows, 'next_cursor': None}
        if path.endswith('/producers'):
            names = ['Legal hold reminders', 'Record workflow', 'Retention reminders'] if self.tag == 'en' else ['تذكيرات التعليق القانوني', 'سير عمل الوثائق', 'تذكيرات الاحتفاظ']
            rows = []
            for code, name, emitted, duration in zip(['hold', 'workflow', 'retention'], names, [640, 384, 128], [.18, .24, .12]):
                for metric, value in [('notifications_emitted', emitted), ('system_seconds', duration), ('system_failure', 0)]:
                    rows.append(dict(producer_code=code, name=name, metric=metric, value=value, observations=1))
            return {'items': [] if self.empty else rows, 'next_cursor': None}
        return {
            'gateways': {'instances': 0 if self.empty else 3, 'unhealthy': 0 if self.empty or self.recovered else 1},
            'alerts': [] if self.empty or self.recovered else [{'metric': 'cleanup_failure'}],
            'metrics': [] if self.empty else [dict(metric=m, value=v, observations=n) for m, v, n in [
                ('send_success', 8240, 8240), ('send_failure', 0, 1), ('purged_messages', 3760, 42),
                ('cleanup_seconds', 4.2, 10), ('cleanup_failure', 0 if self.recovered else 1, 1),
                ('catchup_failure', 0, 1), ('system_failure', 0, 1), ('test_success', 12, 12),
            ]],
            'retention': {k: 0 if self.empty else v for k, v in dict(
                approaching_expiry=180, active_inbox=12480, restorable_inbox=640,
                active_outbox=8320, restorable_outbox=320, expired_retained=96,
                eligible_groups=12, oldest_eligible_group='05 Oct 2026 · 09:20',
                oldest_expired_candidate='05 Oct 2026 · 09:18', group_members=21760,
                expired_retained_by_group=96, largest_group=420, group_failures=0,
            ).items()},
            'can_view_audit': True,
        }


@ui.page('/{tag}')
async def page(tag: str):
    tag = 'ar' if tag == 'ar' else 'en'
    direction = 'rtl' if tag == 'ar' else 'ltr'
    set_active_messages(AR if tag == 'ar' else {})
    ui.query('html').props(f'lang={tag} dir={direction}')
    # Use the actual application's style surface, including its RTL contracts.
    ui.add_css(APP_STYLES)
    ui.colors(primary='#268bd2', positive='#2f9e44', warning='#e9a23b', negative='#dc5050')
    api = FixtureApi(tag)
    with ui.row().classes('w-full items-center gap-3'):
        ui.link('English / LTR', '/en')
        ui.link('العربية / RTL', '/ar')
        ui.button('Fixture: healthy', on_click=lambda: setattr(api, 'recovered', True))
        ui.button('Fixture: empty', on_click=lambda: setattr(api, 'empty', True))
        ui.button('Fixture: failed read', on_click=lambda: setattr(api, 'fail', True))
    with ui.column().classes('w-full mx-auto gap-0').style('max-width:1200px'):
        ui.label(render_message('messaging.monitor.title')).classes('text-2xl font-semibold px-3 pt-4')
        ui.label('Illustrative data / بيانات توضيحية').classes('text-xs text-slate-500 px-3')
        await messaging_monitor(api=api, container=ui.column().classes('w-full'), active=lambda: True,
                                format_timestamp=str,
                                open_audit=lambda: ui.notify('Fixture audit shortcut: system_notification'))


if __name__ == '__main__':
    ui.run(host='127.0.0.1', port=18095, reload=False, show=False, title='Monitor overview verification')
