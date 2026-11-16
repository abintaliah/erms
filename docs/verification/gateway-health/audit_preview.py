"""Database-free preview of the real Monitor callback and audit page handler."""
from pathlib import Path
import json,inspect
from typing import Any,Callable
from nicegui import ui
from frontend.webui.i18n_catalogue import set_active_messages,render_message
from frontend.webui.audit_labels import audit_entity_type_label
from frontend.webui.api_client import ApiError
from frontend.webui.messaging_monitor import messaging_monitor
from frontend.webui.interaction.tests.test_messaging_monitor_navigation import application_audit_callback
ROOT=Path(__file__).resolve().parents[3]
AR={r['message_key']:r['translated_text'] for r in json.loads((ROOT/'frontend/webui/i18n/messages.ar.generated.json').read_text())['items']}
class Api:
 def cancel_pending_reads(self):pass
 async def request(self,method,path,**kwargs):
  if path.endswith(('/gateways','/producers')):return {'items':[],'next_cursor':None}
  return {'alerts':[],'metrics':[],'retention':{},'can_view_audit':True}
 async def event_history_filter_options(self):return {'entity_types':['record','system_notification'],'operations':[],'sources':[],'actor_types':[]}
 async def search_request(self,resource,payload):
  print('Audit search:',json.dumps(payload),flush=True)
  return {'items':[],'total':0}
@ui.page('/{tag}')
async def page(tag:str):
 tag='ar' if tag=='ar' else 'en'
 set_active_messages(AR if tag=='ar' else {})
 with ui.row():
  ui.link('English / LTR','/en');ui.link('العربية / RTL','/ar')
 with ui.element('main').props('dir='+('rtl' if tag=='ar' else 'ltr')).classes('w-full'):
  api=Api();host=ui.column().classes('w-full')
  namespace=dict(state={},api=api,inspect=inspect,Callable=Callable,Any=Any,ui=ui,render_message=render_message,
   audit_entity_type_label=audit_entity_type_label,register_navigation=lambda *args:None,show_authenticated_view=lambda:None,
   title=ui.label(),subtitle=ui.label(),guidance=ui.label(),add_button=ui.button(),add_record_button=ui.button(),search_bar=ui.row(),aggregation_mode_bar=ui.row(),table_container=host,ApiError=ApiError,
   hydrate_historical_audit_identities=lambda rows:None,render_event_timeline=lambda rows,container:None,set_connection_status=lambda connected:None,event_label=str)
  callback=application_audit_callback(namespace)
  ui.button('Sidebar audit fixture',on_click=lambda:namespace['guarded_page_navigation'](namespace['select_audit_trail']))
  await messaging_monitor(api=api,container=host,active=lambda:True,format_timestamp=str,open_audit=callback)
if __name__ == '__main__':
 ui.run(host='127.0.0.1',port=18092,reload=False,show=False,title='Messaging audit shortcut verification')
