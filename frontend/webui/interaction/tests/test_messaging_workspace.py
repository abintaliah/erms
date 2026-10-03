"""Real NiceGUI controls with bounded fake data; no database connections."""

import ast
import asyncio
import json
from pathlib import Path
from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest
from nicegui import ui, background_tasks
from nicegui.testing import User
from frontend.webui.app import (
    relationship_select,
    relationship_options,
    relationship_search_query,
)
from frontend.webui.api_client import ApiError
from frontend.webui.i18n_catalogue import render_message_plain, set_active_messages
from frontend.webui.messaging_workspace import messaging_workspace

pytest_plugins = ["nicegui.testing.user_plugin"]
pytestmark = pytest.mark.asyncio
ROOT = Path(__file__).parents[2]
BINDING = next(
    n
    for n in ast.walk(ast.parse((ROOT / "app.py").read_text()))
    if isinstance(n, ast.FunctionDef) and n.name == "bind_remote_relationship_select"
)


class Api:
    def __init__(self):
        self.calls = []
        self.block = None
        self.sent = []

    async def full_text_search(self, payload):
        self.calls.append(("full_text_search", payload))
        return {"items": [{"type": "record", "record": {"id": 5, "title": "Visible record", "security_level_id": 1,
                           "record_number": "R-5"}}], "next_cursor": None}

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if self.block:
            await self.block.wait()
        if path.endswith("/capabilities"):
            return {
                "limits": {
                    "MAX_SELECTORS_PER_SEND": 100,
                    "MAX_RECIPIENTS_PER_SEND": 2000,
                    "MAX_RESOURCE_LINKS": 50,
                },
                "security_levels": [{"id": 1, "name": "General"}],
                "default_security_level_id": 1,
            }
        if path.endswith("/recipients/validate"):
            return {"expanded_recipient_count": 1}
        if "/recipients/" in path:
            return {
                "items": [
                    {"id": 2, "name": "Recipient", "eligible": True, "email": "recipient@example.test"},
                    {
                        "id": 3,
                        "name": "Restricted recipient",
                        "eligible": False,
                        "reason_code": "message_recipient_clearance_required",
                    },
                ],
                "has_more": False,
            }
        if "/resources/" in path:
            return {
                "items": [{"id": 5, "title": "Visible record", "eligible": True}],
                "has_more": False,
            }
        if path.endswith("/send"):
            self.sent.append(kwargs["json"])
            return {"envelope_id": "sent"}
        return {"items": [], "has_more": False, "next_cursor": None}

    async def administration_reference_page(self, *args, **kwargs):
        self.calls.append(("reference", args[0], kwargs))
        return {"items": [{"id": 1, "name": "General", "level_number": 0}]}

    async def get(self, *args):
        return {"id": 1, "name": "General", "level_number": 0}


async def setup(user, language="en", exchange=True, browse=None):
    api = Api()
    alive = {"value": True}
    scope = dict(
        ui=ui,
        api=api,
        Any=Any,
        Callable=Callable,
        asyncio=asyncio,
        json=json,
        background_tasks=background_tasks,
        ApiError=ApiError,
        error_message=str,
        render_message_plain=render_message_plain,
        relationship_options=relationship_options,
        relationship_search_query=relationship_search_query,
    )
    exec(
        compile(
            ast.Module(body=[BINDING], type_ignores=[]), "<shared-selector>", "exec"
        ),
        scope,
    )

    @ui.page("/messaging-test")
    async def page():
        if language == "ar":
            set_active_messages(
                {
                    r["message_key"]: r["translated_text"]
                    for r in json.loads(
                        (ROOT / "i18n/messages.ar.generated.json").read_text()
                    )["items"]
                }
            )
        else:
            set_active_messages({})
        await messaging_workspace(
            api=api,
            container=ui.column(),
            mailbox="inbox",
            can_exchange=exchange,
            relationship_select=relationship_select,
            bind_relationship=scope["bind_remote_relationship_select"],
            open_resource=AsyncMock(),
            format_timestamp=str,
            active=lambda: alive["value"],
            browse_recipients=browse,
        )

    await user.open("/messaging-test")
    return api, alive


async def test_compose_uses_shared_bounded_selector_and_sends_new_content(user: User):
    api, _ = await setup(user)
    await user.should_see("No messages to show")
    user.find("Compose").click()
    await user.should_see("Subject")
    control = next(c for c in user.find(ui.select).elements if c.label == "To")
    control.options = {6: "User · Recipient"}
    control.update()
    control.value = [6]
    await user.should_see("Current recipient count: 1")
    subject = next(c for c in user.find(ui.input).elements if c.label == "Subject")
    subject.value = "A new subject"
    next(iter(user.find(ui.editor).elements)).value = "<p>New content only</p>"
    user.find("Send", kind=ui.button).click()
    await user.should_see("Message sent")
    assert api.sent[0]["subject"] == "A new subject"
    assert all(call[2].get("params", {}).get("limit", 25) <= 25 for call in api.calls)


@pytest.mark.parametrize(
    "language,empty", [("en", "No messages to show"), ("ar", "لا توجد رسائل لعرضها")]
)
async def test_system_only_inbox_hides_compose_and_reopens_fresh(
    user: User, language, empty
):
    api, _ = await setup(user, language, exchange=False)
    await user.should_see(empty)
    assert not any(
        b.text in ("Compose", "إنشاء رسالة") for b in user.find(ui.button).elements
    )
    label = "Refresh" if language == "en" else "تحديث"
    user.find(label).click()
    await asyncio.sleep(0.05)
    await user.should_see(empty)
    assert sum(path.endswith("/inbox") for _, path, _ in api.calls) == 2


async def test_abandoned_refresh_cannot_render_into_another_page(user: User):
    api, alive = await setup(user)
    api.block = asyncio.Event()
    user.find("Refresh").click()
    await asyncio.sleep(0.05)
    alive["value"] = False
    api.block.set()
    await asyncio.sleep(0.05)
    await user.should_see("Loading messages…")


async def test_structured_resource_editor_roundtrip(user: User):
    api, _ = await setup(user)
    user.find("Compose").click()
    await user.should_see("Subject")
    recipient = next(c for c in user.find(ui.select).elements if c.label == "To")
    recipient.options = {6: "User · Recipient"}
    recipient.update()
    recipient.value = [6]
    await user.should_see("Current recipient count: 1")
    user.find("Add resources", kind=ui.button).click()
    await user.should_see("Search text")
    next(c for c in user.find(ui.input).elements if c.label == "Search text").value = "Visible"
    user.find(kind=ui.button, content="Search").click()
    await user.should_see("Visible record")
    check = next(c for c in user.find(ui.checkbox).elements if c.props.get("aria-label") == "Visible record")
    check.value = True
    user.find("Add selected", kind=ui.button).click()
    await asyncio.sleep(0.1)
    subject = next(c for c in user.find(ui.input).elements if c.label == "Subject")
    assert next(iter(user.find(ui.editor).elements)).value == ""
    subject.value = "Linked resource"
    await asyncio.sleep(0.05)
    user.find("Send", kind=ui.button).click()
    await user.should_see("Message sent")
    link = api.sent[0]["resource_links"][0]
    assert link["resource_kind"] == "record" and link["target_id"] == 5
    assert link["link_token"] in api.sent[0]["body_rich_text"]


async def test_shared_remote_selector_retains_selection_and_disables_explained_results(
    user: User,
):
    api = Api()
    scope = dict(
        ui=ui,
        api=api,
        Any=Any,
        Callable=Callable,
        asyncio=asyncio,
        json=json,
        background_tasks=background_tasks,
        ApiError=ApiError,
        error_message=str,
        render_message_plain=render_message_plain,
        relationship_options=relationship_options,
        relationship_search_query=relationship_search_query,
    )
    exec(
        compile(
            ast.Module(body=[BINDING], type_ignores=[]), "<shared-selector>", "exec"
        ),
        scope,
    )
    controls = {}

    @ui.page("/shared-messaging-selector")
    async def page():
        control = relationship_select("Recipient", {9: "Retained recipient"}, value=9, remote=True)

        async def selected(identity):
            return {"id": identity, "name": "Retained recipient", "eligible": True}

        load = scope["bind_remote_relationship_select"](
            control,
            "users",
            ("name",),
            ("name",),
            page_loader=lambda q: api.request(
                "GET", "/recipients/user", params={"q": q, "limit": 25}
            ),
            selected_loader=selected,
            option_reason=lambda row: None if row.get("eligible") else "No clearance",
        )
        controls.update(control=control, load=load)
        await load("Recipient")

    await user.open("/shared-messaging-selector")
    control = controls["control"]
    assert control.value == 9 and 9 in control.options
    assert "No clearance" not in control.options[3]
    assert control.option_details[3]["reason"] == "No clearance"
    assert control.option_details[2]["email"] == "recipient@example.test"
    control.update()
    rendered = {key: row for key, row in zip(control.options, control._props['options'])}
    assert rendered[3]['reason'] == 'No clearance'
    assert rendered[2]['email'] == 'recipient@example.test'
    assert list(control.options).index(3) in json.loads(
        control._props[":option-disable"].split(" => ", 1)[1].split(".includes", 1)[0]
    )
    assert api.calls[-1][2]["params"]["limit"] == 25


async def test_compose_security_search_respects_current_clearance(user: User):
    api, _ = await setup(user)
    user.find("Compose").click()
    await user.should_see("Subject")
    level = next(
        c for c in user.find(ui.select).elements if c.label == "Security level"
    )

    async def levels(*args, **kwargs):
        api.calls.append(("reference", args[0], kwargs))
        return {
            "items": [
                {"id": 1, "name": "General", "level_number": 0},
                {"id": 99, "name": "Above clearance", "level_number": 99},
            ]
        }

    api.administration_reference_page = levels
    # Invoke the genuine shared remote-search event registered on the control.
    listener = next(
        listener
        for listener in level._event_listeners.values()
        if listener.type == "inputValue"
    )
    from nicegui import events

    events.handle_event(
        listener.handler,
        events.GenericEventArguments(sender=level, client=level.client, args="Gen"),
    )
    await asyncio.sleep(0.4)
    assert 1 in level.options and 99 not in level.options
    assert any(
        method == "reference" and kwargs.get("filters") == {"assignable": True}
        for method, _, kwargs in api.calls
    )

    recipient = next(c for c in user.find(ui.select).elements if c.label == "To")
    listener = next(x for x in recipient._event_listeners.values() if x.type == "inputValue")
    events.handle_event(listener.handler, events.GenericEventArguments(sender=recipient, client=recipient.client, args="Re"))
    await asyncio.sleep(0.4)
    assert recipient.options[7] == "Role · Recipient"
    assert all(call[2]["params"]["security_level_id"] == 1 for call in api.calls if "/recipients/" in call[1] and "params" in call[2])


async def emit_query(control, query):
    from nicegui import events
    listener = next(x for x in control._event_listeners.values() if x.type == 'inputValue')
    events.handle_event(listener.handler, events.GenericEventArguments(sender=control, client=control.client, args=query))
    await asyncio.sleep(0.3)


async def test_two_character_mixed_search_keeps_to_and_cc_separate(user: User):
    api, _ = await setup(user)
    user.find('Compose').click()
    await user.should_see('Subject')
    controls = {c.label:c for c in user.find(ui.select).elements}
    assert 'To' in controls and 'Cc' in controls and 'Recipient kind' not in controls
    to, cc = controls['To'], controls['Cc']
    await emit_query(to, 'R')
    assert not any('/recipients/' in call[1] for call in api.calls)
    await emit_query(to, 'Re')
    assert set(to.options) == {6,7,8,9,10,11}
    assert 'User' in to.options[6] and 'Role' in to.options[7] and 'Organizational unit' in to.options[8]
    to.value = [6]
    await user.should_see('Current recipient count: 1')
    await emit_query(cc, 'Re')
    cc.value = [7,8]
    await asyncio.sleep(0.1)
    await emit_query(to, '')
    assert to.value == [6] and to.options[6] == 'User · Recipient'
    assert cc.value == [7,8]
    cc.value = [8]
    await asyncio.sleep(0.1)
    next(c for c in user.find(ui.input).elements if c.label=='Subject').value='Mixed recipients'
    user.find('Send',kind=ui.button).click()
    await user.should_see('Message sent')
    assert api.sent[0]['selectors'] == [
        {'recipient_type':'to','selector_kind':'user','target_id':2},
        {'recipient_type':'cc','selector_kind':'org_unit','target_id':2},
    ]


async def test_shared_browser_can_add_to_either_address_field(user: User):
    async def browse(**kwargs):
        assert kwargs['selection_mode'] == 'all'
        assert await kwargs['on_selection']({'type':'role','id':2})
    api, _ = await setup(user, browse=browse)
    user.find('Compose').click()
    await user.should_see('Subject')
    buttons = list(user.find('Browse organization structure',kind=ui.button).elements)
    assert len(buttons)==2
    for i,button in enumerate(sorted(buttons,key=lambda x:x.id)):
        button.mark('browse'+str(i))
        user.find(marker='browse'+str(i)).click()
        await asyncio.sleep(0.1)
    controls = {c.label:c for c in user.find(ui.select).elements}
    assert controls['To'].value == controls['Cc'].value == [7]


async def test_abandoned_recipient_search_does_not_update_controls(user: User):
    api, alive = await setup(user)
    user.find('Compose').click()
    await user.should_see('Subject')
    control = next(c for c in user.find(ui.select).elements if c.label == 'To')
    api.block = asyncio.Event()
    await emit_query(control, 'Re')
    alive['value'] = False
    api.block.set()
    await asyncio.sleep(.1)
    assert control.options == {}
    assert len([call for call in api.calls if '/recipients/' in call[1]]) == 3


@pytest.mark.parametrize('language', ['en', 'ar'])
async def test_due_date_guidance_follows_action_field_visibility(user: User, language):
    await setup(user, language=language)
    user.find('Compose' if language=='en' else 'إنشاء رسالة').click()
    await user.should_see('Subject' if language=='en' else 'الموضوع')
    await user.should_see('Action required' if language=='en' else 'يتطلب إجراءً')
    action = next(c for c in user.find(ui.checkbox).elements if c.text == ('Action required' if language=='en' else 'يتطلب إجراءً'))
    due = next(c for c in action.client.elements.values() if isinstance(c,ui.input) and c.props.get('type')=='date')
    help_text = 'The due date uses your working timezone and is informational.' if language=='en' else 'يُستخدم نطاقك الزمني لتاريخ الاستحقاق، وهو تاريخ إرشادي.'
    guidance = next(c for c in action.client.elements.values() if isinstance(c,ui.label) and c.text == help_text)
    assert not due.visible and not guidance.visible
    action.value=True
    await asyncio.sleep(.05)
    assert due.visible and guidance.visible
    action.value=False
    await asyncio.sleep(.05)
    assert not due.visible and not guidance.visible


async def test_add_resource_explains_failed_eligibility_recheck(user: User):
    api, _ = await setup(user)
    user.find('Compose').click()
    await user.should_see('Subject')
    user.find("Add resources", kind=ui.button).click()
    await user.should_see("Search text")
    next(c for c in user.find(ui.input).elements if c.label == "Search text").value = "Visible"
    user.find(kind=ui.button, content="Search").click()
    await user.should_see("Visible record")
    check = next(c for c in user.find(ui.checkbox).elements if c.props.get("aria-label") == "Visible record")
    check.value = True
    original = api.request

    async def unavailable(method, path, **kwargs):
        if '/resources/' in path:
            return {'items': [{'id': 5, 'title': 'Visible record', 'eligible': False,
                               'reason_code': 'message_resource_level_too_high'}]}
        return await original(method, path, **kwargs)

    api.request = unavailable
    user.find("Add selected", kind=ui.button).click()
    await user.should_see(render_message_plain('messaging.reason.message_resource_level_too_high'))
    editor = next(iter(user.find(ui.editor).elements))
    assert 'data-wathiq-link' not in (editor.value or '')


async def test_resource_batch_recheck_is_all_or_nothing(user: User):
    api, _ = await setup(user)
    async def search(payload):
        return {'items': [{'type': 'record', 'record': {'id': i, 'title': 'Candidate '+str(i), 'security_level_id': 1}}
                          for i in (5, 6)], 'next_cursor': None}
    api.full_text_search = search
    user.find('Compose').click()
    await user.should_see('Subject')
    user.find('Add resources', kind=ui.button).click()
    await user.should_see('Search text')
    next(c for c in user.find(ui.input).elements if c.label == 'Search text').value = 'Candidate'
    user.find(kind=ui.button, content='Search').click()
    await user.should_see('Candidate 5')
    for check in user.find(ui.checkbox).elements:
        if check.props.get('aria-label') in ('Candidate 5', 'Candidate 6'):
            check.value = True
    original = api.request
    async def recheck(method, path, **kwargs):
        if '/resources/' in path:
            identity = kwargs['params']['target_id']
            return {'items': [{'id': identity, 'title': 'Candidate '+str(identity),
                              'eligible': identity == 5,
                              'reason_code': None if identity == 5 else 'message_resource_unavailable'}]}
        return await original(method, path, **kwargs)
    api.request = recheck
    user.find('Add selected', kind=ui.button).click()
    await user.should_see(render_message_plain('messaging.reason.message_resource_unavailable'))
    assert 'data-wathiq-link' not in next(iter(user.find(ui.editor).elements)).value
    await user.should_see('Selected resources: 2')


async def test_resource_markers_do_not_become_authored_body():
    from frontend.webui.messaging_workspace import body_without_resources, body_with_resource_markers
    legacy = '<p>Authored text</p><p><span data-wathiq-link="abc">Old record title</span></p><p>After</p>'
    assert body_without_resources(legacy) == '<p>Authored text</p><p>After</p>'
    stored = body_with_resource_markers(legacy, [{'link_token': 'new'}])
    assert 'Old record title' not in stored
    assert stored == '<p>Authored text</p><p>After</p><span data-wathiq-link="new"></span>'
