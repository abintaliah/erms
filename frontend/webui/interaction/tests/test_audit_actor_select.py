"""Two-character suggestions, retained identities and stale/failed reads."""
import asyncio
import json
from pathlib import Path
import pytest
from nicegui import ui,events
from nicegui.testing import User
from frontend.webui.remote_select import RemoteSelect
from frontend.webui.audit_actor_select import bind_audit_actor_select,actor_condition
from frontend.webui.i18n_catalogue import set_active_messages,render_message_plain
from frontend.webui.api_client import ApiError

pytest_plugins=['nicegui.testing.user_plugin']
pytestmark=pytest.mark.asyncio


@pytest.mark.parametrize('tag',['en','ar'])
async def test_directory_selector_bound_identity_and_abandonment(user:User,tag):
    calls=[];errors=[];objects={};active={'value':True};gate=asyncio.Event()
    messages={r['message_key']:r['translated_text'] for r in json.loads((Path(__file__).parents[2]/'i18n/messages.ar.generated.json').read_text())['items']} if tag=='ar' else {}
    old={'actor_user_id':444,'actor_name':'Directory Person','actor_email':'old@example.invalid','actor_type':'user'}
    fresh={'actor_user_id':555,'actor_name':'Fresh Person','actor_email':'fresh@example.invalid','actor_type':'user'}
    class Api:
        async def audit_actors(self,q,**scope):
            calls.append((q,scope))
            if q in ('Stale','Abandon'):
                try: await gate.wait()
                except asyncio.CancelledError: await gate.wait()
                return {'items':[old],'has_more':False}
            if q=='Error': raise ApiError(503,'fixture error')
            return {'items':[] if q=='None' else [fresh] if q=='Fresh' else [old],'has_more':q=='Bound'}
    @ui.page('/actor-selector')
    def page():
        set_active_messages(messages)
        control=RemoteSelect({},label='Actor fixture',with_input=True,clearable=True)
        status=ui.label()
        state,selected,reset=bind_audit_actor_select(control,status,api=Api(),active=lambda:active['value'],scope=lambda:{'entity_type':'record','actor_type':'user'},on_error=errors.append)
        objects.update(control=control,status=status,state=state,selected=selected,reset=reset)
    await user.open('/actor-selector')
    control=objects['control']
    def type_query(query):
        with user.client:
            event=events.GenericEventArguments(sender=control,client=user.client,args=query)
            for listener in control._event_listeners.values():
                if listener.type=='inputValue':events.handle_event(listener.handler,event)
    type_query('D');await asyncio.sleep(.25);assert calls==[]
    type_query('  De  ');await asyncio.sleep(.25)
    assert calls[-1]==('De',{'entity_type':'record','actor_type':'user'})
    assert control.options['user:444']=='Directory Person — old@example.invalid'
    control.value='user:444';await asyncio.sleep(.01)
    before_selection_sync=len(calls)
    type_query(control.options['user:444']);await asyncio.sleep(.25)
    assert len(calls)==before_selection_sync and objects['state']['query']==''
    assert actor_condition(objects['selected']())=={'field':'actor_user_id','operator':'eq','value':444}
    type_query('Fresh');await asyncio.sleep(.25)
    assert 'user:444' in control.options and 'user:555' in control.options
    objects['reset']();assert control.value is None and objects['state']['query']==''
    type_query('Stale');await asyncio.sleep(.25)
    type_query('Fresh');await asyncio.sleep(.25);gate.set();await asyncio.sleep(.05)
    assert list(control.options)==['user:555']
    type_query('None');await asyncio.sleep(.25)
    assert objects['state']['query']=='None' and objects['selected']() is None
    assert objects['status'].text==(messages.get('audit.filter.no_actors') or render_message_plain('audit.filter.no_actors'))
    type_query('Bound');await asyncio.sleep(.25)
    assert objects['status'].text==(messages.get('audit.filter.refine_actors') or render_message_plain('audit.filter.refine_actors'))
    type_query('Error');await asyncio.sleep(.25)
    assert errors and control.options=={}
    assert objects['status'].text==(messages.get('audit.filter.actors_failed') or render_message_plain('audit.filter.actors_failed'))
    gate.clear();type_query('Abandon');await asyncio.sleep(.25)
    active['value']=False;gate.set();await asyncio.sleep(.05)
    assert control.options=={}


async def test_snapshot_actor_without_user_id_uses_exact_nullable_identity():
    expression=actor_condition({'actor_user_id':None,'actor_name':'Worker','actor_email':None,'actor_type':'automated_process'})
    assert expression=={'and':[{'field':'actor_user_id','operator':'is_null'},{'field':'actor_name','operator':'eq','value':'Worker'},{'field':'actor_email','operator':'is_null'},{'field':'actor_type','operator':'eq','value':'automated_process'}]}
