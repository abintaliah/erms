"""Database-free visual fixture for the real Message Monitor renderer."""

import json
from pathlib import Path
from nicegui import ui
from frontend.webui.messaging_monitor import messaging_monitor
from frontend.webui.i18n_catalogue import set_active_messages

ROOT=Path(__file__).resolve().parents[3]
AR={r['message_key']:r['translated_text'] for r in json.loads((ROOT/'frontend/webui/i18n/messages.ar.generated.json').read_text())['items']}

class FixtureApi:
 def __init__(self):
  self.recovered=False
 async def request(self,method,path,**kwargs):
  if path.endswith('/gateways'):
   base=dict(observed_at='2026-10-05 12:00:00 +04:00',notifications_received=12,active_connections=1,listener_generation=1,slow_disconnects=0,last_notification_at='2026-10-05 11:59:50 +04:00')
   return {'items':[
    dict(base,instance_id='ad044288-d940-47e2-a31b-3d876d6fcffa',host_addresses=['127.0.0.1'],api_port=8001,listener_connected=True,health_status='connected'),
    dict(base,instance_id='ea8cfcb9-0429-47e5-80ab-05035e3cc6dc',host_addresses=['10.0.0.2','::1'],api_port=8002,listener_connected=True,health_status='connected' if self.recovered else 'overdue'),
    dict(base,instance_id='legacy-pre-upgrade',host_addresses=[],api_port=None,listener_connected=False,health_status='disconnected')
   ],'next_cursor':None}
  if path.endswith('/producers'):return {'items':[],'next_cursor':None}
  return {'alerts':[],'metrics':[],'retention':{'approaching_expiry':0},'can_view_audit':False}

@ui.page('/{tag}')
async def page(tag:str):
 tag='ar' if tag=='ar' else 'en'
 set_active_messages(AR if tag=='ar' else {})
 api=FixtureApi()
 with ui.row():
  ui.link('English / LTR','/en')
  ui.link('العربية / RTL','/ar')
  ui.button('Fixture: resume heartbeat',on_click=lambda:setattr(api,'recovered',True))
 with ui.element('main').props('dir='+('rtl' if tag=='ar' else 'ltr')).classes('w-full'):
  await messaging_monitor(api=api,container=ui.column().classes('w-full'),active=lambda:True,format_timestamp=str)
if __name__ == '__main__':
 ui.run(host='127.0.0.1',port=18091,reload=False,show=False,title='Gateway Monitor verification')
