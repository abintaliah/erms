"""Organization-wide human-message audience on disposable databases only."""
import pytest
from .test_messaging import account, payload, post, db, PREFIX
from .test_global_privilege_enforcement import _bearer


def everyone(kind="to"):
    return dict(selector_kind="everyone", target_id=None, recipient_type=kind)


def test_everyone_cc_deduplicates_to_and_is_informational(client):
    sender, sender_id, _ = account(client)
    to_token, to_id, _ = account(client)
    cc_token, cc_id, _ = account(client)
    _, excluded, _ = account(client, privileges=())
    response = post(client, sender, payload(action_required=True, selectors=[everyone("cc"),
        dict(selector_kind="user", target_id=to_id, recipient_type="to")]))
    assert response.status_code == 200, response.text
    sent = response.json()
    deliveries = {d["recipient_user_id"]: d for d in sent["deliveries"]}
    assert len(deliveries) == len(sent["deliveries"])
    assert sender_id not in deliveries and excluded not in deliveries
    assert deliveries[to_id]["recipient_type"] == "to"
    assert deliveries[cc_id]["recipient_type"] == "cc"
    cc = client.get(PREFIX + "/inbox/" + deliveries[cc_id]["id"], headers=_bearer(cc_token)).json()
    assert cc["action_status"] is None
    to = client.get(PREFIX + "/inbox/" + deliveries[to_id]["id"], headers=_bearer(to_token)).json()
    assert to["action_status"] == "outstanding"
    # New membership cannot alter a sent envelope.
    _, late_id, _ = account(client)
    with db() as c:
        assert not c.execute("SELECT 1 FROM message_deliveries WHERE envelope_id=%s AND recipient_user_id=%s", (sent["envelope_id"], late_id)).fetchone()


def test_everyone_draft_roundtrip_and_send(client):
    sender, sender_id, _ = account(client)
    _, recipient_id, _ = account(client)
    draft = client.post(PREFIX + "/drafts", headers=_bearer(sender), json={"subject": "Memo", "body_rich_text": "<p>Memo</p>", "selectors": [everyone()]} )
    assert draft.status_code == 200, draft.text
    row = draft.json()
    assert row["selectors"] == [everyone()]
    from uuid import uuid4
    response = client.post(PREFIX + "/drafts/" + row["id"] + "/send", headers=_bearer(sender), json={"version": row["version"], "request_id": str(uuid4())})
    assert response.status_code == 200, response.text
    assert recipient_id in {d["recipient_user_id"] for d in response.json()["deliveries"]}


@pytest.mark.parametrize("selectors", [
    [everyone(), dict(selector_kind="user",target_id=1,recipient_type="cc")],
    [everyone(), everyone("cc")],
    [everyone("cc"), dict(selector_kind="user",target_id=1,recipient_type="cc")],
    [everyone("cc")],
    [dict(selector_kind="everyone",target_id=1,recipient_type="to")],
])
def test_everyone_invalid_compositions_rejected(client, selectors):
    sender, _, _ = account(client)
    assert post(client, sender, payload(selectors=selectors)).status_code == 422
    # Incomplete Cc-only drafts are valid, but conflicting compositions are not.
    if selectors != [everyone("cc")]:
        assert client.post(PREFIX + "/drafts", headers=_bearer(sender), json={"selectors": selectors}).status_code == 422


def test_everyone_recipient_limit_and_clearance(client, monkeypatch):
    sender, sender_id, sender_role = account(client)
    _, recipient_id, _ = account(client)
    from backend.services.api.messaging import service
    monkeypatch.setitem(service.LIMITS, "MAX_RECIPIENTS_PER_SEND", 1)
    _, extra_id, _ = account(client)
    assert post(client, sender, payload(selectors=[everyone()])).json()["detail"]["code"] == "message_recipient_limit"
    monkeypatch.setitem(service.LIMITS, "MAX_RECIPIENTS_PER_SEND", 2000)
    with db() as c:
        highest = c.execute("SELECT id FROM security_levels ORDER BY level_number DESC LIMIT 1").fetchone()["id"]
        c.execute("UPDATE roles SET security_level_id=%s WHERE id=%s", (highest,sender_role))
    sent = post(client, sender, payload(security_level_id=highest, selectors=[everyone()]))
    # Every other test account has only the lowest clearance; no leak to them.
    if sent.status_code == 200:
        assert recipient_id not in {d["recipient_user_id"] for d in sent.json()["deliveries"]}
        assert extra_id not in {d["recipient_user_id"] for d in sent.json()["deliveries"]}
    else:
        assert sent.status_code == 422, sent.text

@pytest.mark.parametrize('kind', ['role', 'org_unit'])
def test_everyone_cc_overlaps_group_to_once(client, kind):
    sender, sender_id, _ = account(client)
    _, recipient_id, role_id = account(client)
    with db() as c:
        unit_id = c.execute('SELECT org_unit_id FROM roles WHERE id=%s', (role_id,)).fetchone()['org_unit_id']
    response = post(client, sender, payload(selectors=[everyone('cc'),
        dict(selector_kind=kind, target_id=role_id if kind == 'role' else unit_id, recipient_type='to')]))
    assert response.status_code == 200, response.text
    matches = [d for d in response.json()['deliveries'] if d['recipient_user_id'] == recipient_id]
    assert len(matches) == 1 and matches[0]['recipient_type'] == 'to'


def test_everyone_localized_in_reading_and_capture_renderer(client, monkeypatch):
    from backend.services.api.messaging import capture
    from time import monotonic
    admin = client.cookies['erms_session']
    account(client)
    result = post(client, admin, payload(selectors=[everyone()]))
    assert result.status_code == 200, result.text
    eid = result.json()['envelope_id']
    rendered = []
    monkeypatch.setattr(capture.capture_pdf, 'render', lambda title, html, *args, **kwargs: rendered.append(html) or b'renderer-input-only')
    with db() as c:
        c.execute("SELECT set_config('app.user_id','1',true)")
        c.execute("SELECT set_config('app.change_reason','Publish isolated test translation',true)")
        c.execute("INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES(1,'ar','Asia/Dubai') ON CONFLICT(user_id) DO UPDATE SET language_tag='ar'")
        c.execute("UPDATE ui_message_translations SET translated_text='الجميع',published_text='الجميع',origin='manual',status='published',needs_review=false WHERE message_key='messaging.field.everyone' AND language_tag='ar'")
        rows = capture.sources(c, 1, eid, eid)
        capture.message_pdf(c, rows[0], 'ar', 'rtl', capture.labels(c, 'ar'), monotonic()+600)
        assert 'الجميع' in rendered[-1] and 'Everyone' not in rendered[-1]
        capture.message_pdf(c, rows[0], 'en', 'ltr', capture.labels(c, 'en'), monotonic()+600)
        assert 'Everyone' in rendered[-1] and 'الجميع' not in rendered[-1]
    message = client.get(PREFIX+'/outbox/'+eid, headers=_bearer(admin)).json()
    assert message['selectors'][0]['display_name'] == 'الجميع'


def test_everyone_is_not_a_producer_configuration_principal():
    from pydantic import ValidationError
    from backend.services.api.messaging.notification_configuration import NotificationSelector
    with pytest.raises(ValidationError):
        NotificationSelector(**everyone())


def test_reply_everyone_to_can_complete_action_without_mixed_selectors(client):
    sender, sender_id, _ = account(client)
    recipient, recipient_id, _ = account(client)
    original = post(client, sender, payload(recipient_id, action_required=True)).json()
    reply = post(client, recipient, payload(selectors=[everyone()], relationship_kind='reply',
        related_delivery_id=original['deliveries'][0]['id'], complete_action=True))
    assert reply.status_code == 200, reply.text
    matches = [d for d in reply.json()['deliveries'] if d['recipient_user_id'] == sender_id]
    assert len(matches) == 1 and matches[0]['recipient_type'] == 'to'
    recipients = client.get(PREFIX+'/outbox/'+original['envelope_id']+'/recipients', headers=_bearer(sender)).json()['items']
    assert recipients[0]['action_status'] == 'completed'
