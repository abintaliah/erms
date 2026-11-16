"""Page-scoped, debounced actor selector; no directory or suggestion cache."""
import asyncio
import json
from .i18n_catalogue import render_message
from .api_client import ApiError


def actor_key(actor):
    if actor['actor_user_id'] is not None:
        return 'user:' + str(actor['actor_user_id'])
    return 'snapshot:' + json.dumps([actor['actor_name'],actor['actor_email'],actor['actor_type']],ensure_ascii=False)


def actor_condition(actor):
    if actor['actor_user_id'] is not None:
        return {'field':'actor_user_id','operator':'eq','value':actor['actor_user_id']}
    return {'and': [
        {'field':field,'operator':'is_null'} if actor.get(field) is None
        else {'field':field,'operator':'eq','value':actor[field]}
        for field in ('actor_user_id','actor_name','actor_email','actor_type')
    ]}


def bind_audit_actor_select(control, status, *, api, active, scope, on_error):
    state = {'query':'','revision':0,'task':None,'actors':{}}

    def selected():
        return state['actors'].get(control.value)

    def retain_selection():
        actor = selected()
        state['actors'] = {control.value:actor} if actor else {}
        control.options = {control.value:control.options[control.value]} if actor else {}

    def invalidate():
        state['revision'] += 1
        task = state['task']
        if task is not None and not task.done():
            task.cancel()
        control.props(remove='loading')

    async def load(query, revision):
        try:
            await asyncio.sleep(.2)
            if not active() or revision != state['revision']:
                return
            control.props('loading')
            result = await api.audit_actors(query, **scope())
            if not active() or revision != state['revision']:
                return
            retain_selection()
            for actor in result['items']:
                key = actor_key(actor)
                state['actors'][key] = actor
                with control.client:
                    control.options[key] = ' — '.join(part for part in (
                        actor['actor_name'] or render_message('audit.filter.unnamed_actor'),
                        actor['actor_email'],
                    ) if part)
            with control.client:
                status.text = (render_message('audit.filter.refine_actors') if result['has_more']
                               else '' if result['items'] else render_message('audit.filter.no_actors'))
            control.update()
        except asyncio.CancelledError:
            return
        except ApiError as error:
            if active() and revision == state['revision']:
                retain_selection()
                control.update()
                with control.client:
                    status.text = render_message('audit.filter.actors_failed')
                on_error(error)
        finally:
            if active() and revision == state['revision']:
                control.props(remove='loading')

    def schedule(event):
        query = str(event.args or '').strip()
        # QSelect also emits input-value while displaying a selected label.
        # That is selection synchronization, not another remote search.
        if selected() and query == control.options.get(control.value):
            return
        invalidate()
        state['query'] = query
        if len(state['query']) < 2:
            retain_selection()
            control.update()
            with control.client:
                status.text = render_message('audit.filter.actor_suggestions_hint')
            return
        state['task'] = asyncio.create_task(load(state['query'],state['revision']))

    def reset():
        invalidate()
        state['query'] = ''
        control.value = None
        state['actors'] = {}
        control.options = {}
        control.update()
        control.run_method('updateInputValue','',True)
        with control.client:
            status.text = render_message('audit.filter.actor_suggestions_hint')

    def changed():
        invalidate()
        state['query'] = ''
        # Keep QSelect's selected display label; clearing it starts filtering
        # again and reopens the popup. Its public hidePopup method is sufficient.
        control.run_method('hidePopup')

    control.on('input-value',schedule)
    control.on_value_change(changed)
    return state, selected, reset
