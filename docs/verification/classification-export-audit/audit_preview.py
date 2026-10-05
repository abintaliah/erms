"""Database-free live EN/AR fixture using the application's Audit Trail page."""
import ast
import asyncio
import json
from pathlib import Path
from typing import Any
from nicegui import ui
from frontend.webui.i18n_catalogue import render_message, set_active_messages
from frontend.webui.audit_labels import audit_entity_type_label
from frontend.webui.event_labels import event_label
from frontend.webui.api_client import ApiError
from frontend.webui.remote_select import RemoteSelect
from frontend.webui.audit_actor_select import bind_audit_actor_select, actor_condition

ROOT = Path(__file__).resolve().parents[3]
TREE = ast.parse((ROOT/'frontend/webui/app.py').read_text())
PAGE = next(n for n in ast.walk(TREE) if isinstance(n,ast.AsyncFunctionDef) and n.name=='select_audit_trail')
STYLES = next(n.args[0].value for n in ast.walk(TREE) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='add_css' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str) and '.erms-card {' in n.args[0].value)
AR = {r['message_key']:r['translated_text'] for r in json.loads((ROOT/'frontend/webui/i18n/messages.ar.generated.json').read_text())['items']}

class Api:
    async def event_history_filter_options(self):
        return dict(entity_types=['classification_scheme','record'],operations=['EXPORT','CREATE'],sources=['api','web_ui'],actor_types=['user','automated_process'])
    async def audit_actors(self, query, **scope):
        await asyncio.sleep(.05)
        actors = [dict(actor_user_id=444, actor_name='Deleted Person', actor_email='old@example.invalid', actor_type='user'),
                  dict(actor_user_id=555, actor_name='Current Person', actor_email='current@example.invalid', actor_type='user')]
        return dict(items=[actor for actor in actors if query.casefold() in (actor['actor_name']+' '+actor['actor_email']).casefold()],has_more=False)

    async def search_request(self,resource,payload):
        await asyncio.sleep(.05)
        return dict(items=[dict(id=1)],total=1000,result_cap=1000,truncated=True)

@ui.page('/{tag}')
async def page(tag:str):
    set_active_messages(AR if tag=='ar' else {})
    ui.query('html').props(f"lang={tag} dir={'rtl' if tag=='ar' else 'ltr'}")
    ui.add_css(STYLES)
    def timeline(rows,container):
        container.clear()
        with container:
            ui.label('Illustrative history row / صف توضيحي لسجل الأحداث').classes('text-sm text-slate-500')
    with ui.column().classes('w-full mx-auto').style('max-width:1200px'):
        ns=dict(state={},ui=ui,api=Api(),Any=Any,render_message=render_message,RemoteSelect=RemoteSelect,bind_audit_actor_select=bind_audit_actor_select,actor_condition=actor_condition,error_message=str,audit_entity_type_label=audit_entity_type_label,event_label=event_label,
            register_navigation=lambda *args:None,show_authenticated_view=lambda:None,title=ui.label().classes('text-2xl'),subtitle=ui.label(),guidance=ui.label(),
            add_button=ui.button(),add_record_button=ui.button(),search_bar=ui.row(),aggregation_mode_bar=ui.row(),table_container=ui.column().classes('w-full'),ApiError=ApiError,
            hydrate_historical_audit_identities=lambda rows:None,render_event_timeline=timeline,set_connection_status=lambda value:None)
        exec(compile(ast.Module(body=[PAGE],type_ignores=[]),'app.py','exec'),ns)
        await ns['select_audit_trail']()

if __name__=='__main__':
    ui.run(host='127.0.0.1',port=18096,reload=False,show=False,title='Audit filter verification fixture')
