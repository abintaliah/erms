"""Shared picker behavior; no database or stack required."""
import asyncio
import pytest
from nicegui import ui
from nicegui.testing import User
from frontend.webui.resource_picker import resource_picker, search_payload
from frontend.webui.i18n_catalogue import set_active_messages

pytest_plugins = ['nicegui.testing.user_plugin']
pytestmark = pytest.mark.asyncio


async def setup(user, *, limit=50, blocked=False, submit=True, on_inspect=None):
    calls, confirmed = [], []
    alive = {'value': True}
    gate = asyncio.Event()
    async def search(payload):
        calls.append(payload)
        if blocked:
            await gate.wait()
        identity = 26 if payload.get('cursor') else 1
        items = []
        for resource in payload['result_types']:
            kind = resource[:-1]
            items.append({'type': kind, kind: {'id': identity, 'title': resource + str(identity),
                                               'security_level_id': 1, 'description': 'Archival description'}})
        items.append({'type': 'record', 'record': {'id': 99, 'title': 'Restricted', 'security_level_id': 9}})
        return {'items': items, 'next_cursor': None if payload.get('cursor') else 'page2'}
    async def confirm(rows, active):
        if active():
            confirmed.extend(rows)
            return True
        return False
    @ui.page('/picker-test')
    async def page():
        set_active_messages({})
        ui.button('Open', on_click=lambda: resource_picker(search=search,
            eligible=lambda row: 'No clearance' if row['security_level_id'] == 9 else None,
            on_inspect=on_inspect, on_confirm=confirm, remaining=lambda: limit, active=lambda: alive['value'],
            on_error=lambda error: pytest.fail(str(error))))
    await user.open('/picker-test')
    user.find('Open').click()
    await user.should_see('Enter a search term, then press Search or Enter.')
    assert calls == []
    if submit:
        next(c for c in user.find(ui.input).elements if c.label == 'Search text').value = 'archive'
        user.find(kind=ui.button, content='Search').click()
    return calls, confirmed, alive, gate


async def test_paging_kind_changes_and_repeat_search_keep_selection(user: User):
    calls, confirmed, _, _ = await setup(user)
    await user.should_see('records1')
    check = next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'records1')
    check.value = True
    restricted = next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'Restricted')
    assert not restricted.enabled
    user.find('Next', kind=ui.button).click()
    await user.should_see('records26')
    next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'records26').value = True
    kind = next(c for c in user.find(ui.select).elements if c.label == 'Resource kind')
    kind.value = 'aggregation'
    user.find(kind=ui.button, content='Search').click()
    await user.should_see('aggregations1')
    next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'aggregations1').value = True
    user.find(kind=ui.button, content='Search').click()
    await asyncio.sleep(.05)
    user.find('Add selected', kind=ui.button).click()
    await asyncio.sleep(.05)
    assert [(r['resource_kind'], r['target_id']) for r in confirmed] == [('record', 1), ('record', 26), ('aggregation', 1)]
    assert all(payload['limit'] == 25 for payload in calls)
    assert calls[1]['cursor'] == 'page2'
    assert 'cursor' not in calls[2]
    assert calls[0]['result_types'] == ['records', 'aggregations']
    assert calls[2]['result_types'] == ['aggregations']


async def test_empty_overlimit_and_cancel_add_nothing(user: User):
    _, confirmed, _, _ = await setup(user, limit=0)
    await user.should_see('records1')
    confirm = next(b for b in user.find(ui.button).elements if b.text == 'Add selected')
    assert not confirm.enabled
    next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'records1').value = True
    assert not confirm.enabled
    await user.should_see('The selected resources exceed the remaining message link limit. Remove some selections.')
    user.find('Cancel', kind=ui.button).click()
    assert confirmed == []


async def test_abandoned_search_cannot_render_results(user: User):
    _, confirmed, alive, gate = await setup(user, blocked=True)
    await user.should_see('Searching…')
    alive['value'] = False
    gate.set()
    await asyncio.sleep(.05)
    await user.should_not_see('records1')
    assert confirmed == []


async def test_single_query_always_uses_full_text_without_preloading(user: User):
    calls, _, _, _ = await setup(user, submit=False)
    query = next(c for c in user.find(ui.input).elements if c.label == 'Search text')
    query.value = '   '
    await asyncio.sleep(.05)
    assert calls == []
    assert not next(b for b in user.find(ui.button).elements if b.text == 'Search').enabled
    kind = next(c for c in user.find(ui.select).elements if c.label == 'Resource kind')
    kind.value = 'aggregation'
    query.value = 'R-42 archival phrase'
    await asyncio.sleep(.05)
    assert calls == []
    user.find(kind=ui.button, content='Search').click()
    await user.should_see('aggregations1')
    assert calls[-1]['aggregation_where'] == {'full_text': {'query': 'R-42 archival phrase', 'sources': ['metadata']}}
    assert calls[-1]['result_types'] == ['aggregations']
    assert 'record_where' not in calls[-1]
    query.value = ''
    await asyncio.sleep(.05)
    assert len(calls) == 1
    assert search_payload('record', ' archives ')['record_where'] == {'full_text': {'query': 'archives', 'sources': ['metadata', 'components']}}
    with pytest.raises(ValueError):
        search_payload('record', ' ')


async def test_editing_query_abandons_inflight_result_without_another_request(user: User):
    calls, _, _, gate = await setup(user, blocked=True)
    await user.should_see('Searching…')
    query = next(c for c in user.find(ui.input).elements if c.label == 'Search text')
    query.value = 'new query'
    gate.set()
    await asyncio.sleep(.05)
    assert len(calls) == 1
    await user.should_not_see('records1')
    await user.should_see('Enter a search term, then press Search or Enter.')


async def test_result_icons_and_details_overlay_preserve_selection(user: User):
    async def inspect(kind, identity, active):
        assert kind == 'record' and identity == 26 and active()
        with ui.dialog() as detail, ui.card():
            ui.label('Metadata overlay')
            ui.button('Close details', on_click=detail.close)
        detail.open()
    calls, confirmed, _, _ = await setup(user, on_inspect=inspect)
    await user.should_see('Archival description')
    assert next(b for b in user.find(ui.button).elements if b.text == 'records1').props['icon'] == 'description'
    assert next(b for b in user.find(ui.button).elements if b.text == 'aggregations1').props['icon'] == 'folder'
    user.find(kind=ui.button, content='Next').click()
    await user.should_see('records26')
    check = next(c for c in user.find(ui.checkbox).elements if c.props.get('aria-label') == 'records26')
    check.value = True
    user.find(kind=ui.button, content='records26').click()
    await user.should_see('Metadata overlay')
    user.find(kind=ui.button, content='Close details').click()
    assert len(calls) == 2 and check.value
    assert next(c for c in user.find(ui.input).elements if c.label == 'Search text').value == 'archive'
    user.find(kind=ui.button, content='Add selected').click()
    await asyncio.sleep(.05)
    assert confirmed[0]['target_id'] == 26
