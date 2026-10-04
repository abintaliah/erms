import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from nicegui import ui
from nicegui.testing import User
from frontend.webui.resource_inspector import resource_inspector
from frontend.webui.api_client import ApiError
from frontend.webui.i18n_catalogue import set_active_messages

pytest_plugins = ['nicegui.testing.user_plugin']
pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize('kind,allowed,language', [('record', True, 'en'), ('record', False, 'en'), ('aggregation', True, 'en'), ('record', True, 'ar')])
async def test_metadata_only_overlay_and_authorized_preview(user: User, kind, allowed, language):
    preview = AsyncMock()
    row = {'id': 7, 'title': 'Inspection target', 'description': 'Detailed description',
           'medium': 'digital', 'security_level_id': 1}
    api = SimpleNamespace(get=AsyncMock(side_effect=lambda resource, identity:
        row if resource == kind+'s' else {'id': identity, 'code': 'GEN', 'name': 'General'}),
        resource_capabilities=AsyncMock(return_value={'view_component': allowed}))
    @ui.page('/inspect-test')
    def page():
        set_active_messages({'translation_inspector.value.no': 'لا'} if language == 'ar' else {})
        ui.button('Inspect', on_click=lambda: resource_inspector(api=api, kind=kind, identity=7,
            active=lambda: True, preview=preview, field_label=lambda value: value,
            format_timestamp=lambda value: str(value or '—'), medium_label=str,
            on_error=lambda error: pytest.fail(str(error))))
    await user.open('/inspect-test')
    user.find(kind=ui.button, content='Inspect').click()
    await user.should_see('Detailed description')
    await user.should_see('لا' if language == 'ar' else 'No')
    assert all(b.text in ('Inspect', 'Close', 'Preview digital components') for b in user.find(ui.button).elements)
    previews = [b for b in user.find(ui.button).elements if b.props.get('icon') == 'visibility']
    assert bool(previews) == (kind == 'record' and allowed)
    if previews:
        user.find(kind=ui.button, content='Preview digital components').click()
        await asyncio.sleep(.05)
        preview.assert_awaited_once_with(row)
    assert api.get.await_count == 2  # One target and one selected security-level ID only.
    user.find(kind=ui.button, content='Close').click()
    assert not next(iter(user.find(ui.dialog).elements)).value


async def test_denied_target_has_no_metadata(user: User):
    errors = []
    api = SimpleNamespace(get=AsyncMock(side_effect=ApiError(403, 'Denied')),
                          resource_capabilities=AsyncMock(return_value={}))
    @ui.page('/inspect-denied')
    def page():
        set_active_messages({})
        ui.button('Inspect', on_click=lambda: resource_inspector(api=api, kind='record', identity=7,
            active=lambda: True, preview=AsyncMock(), field_label=str,
            format_timestamp=str, medium_label=str, on_error=errors.append))
    await user.open('/inspect-denied')
    user.find(kind=ui.button, content='Inspect').click()
    await asyncio.sleep(.1)
    assert len(errors) == 1
    await user.should_not_see('Detailed description')


async def test_close_while_loading_discards_late_metadata(user: User):
    gate = asyncio.Event()
    async def get(*args):
        await gate.wait()
        return {'id': 7, 'title': 'Late private metadata'}
    api = SimpleNamespace(get=get, resource_capabilities=AsyncMock(return_value={}))
    @ui.page('/inspect-slow')
    def page():
        set_active_messages({})
        ui.button('Inspect', on_click=lambda: resource_inspector(api=api, kind='record', identity=7,
            active=lambda: True, preview=AsyncMock(), field_label=str,
            format_timestamp=str, medium_label=str, on_error=lambda error: pytest.fail(str(error))))
    await user.open('/inspect-slow')
    user.find(kind=ui.button, content='Inspect').click()
    await user.should_see('Close')
    user.find(kind=ui.button, content='Close').click()
    # NiceGUI's user simulator does not emit the browser's hide transition.
    dialog = next(iter(user.find(ui.dialog).elements))
    from nicegui import events
    for listener in dialog._event_listeners.values():
        if listener.type == 'hide':
            events.handle_event(listener.handler, events.GenericEventArguments(sender=dialog, client=dialog.client,args=None))
    gate.set()
    await asyncio.sleep(.1)
    await user.should_not_see('Late private metadata')
