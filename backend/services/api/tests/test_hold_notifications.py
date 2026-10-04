"""Legal-hold producer acceptance tests: disposable messaging runner only."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi import HTTPException

from .test_messaging import account, db
from .test_global_privilege_enforcement import _bearer
from backend.services.api import hold_notifications as hn
from backend.services.api.messaging import notification_registry as registry
from backend.services.api.messaging.transactions import run
from backend.services.api.messaging import notification_configuration as cfg
from tools.configure_hold_notifications import configure

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def enabled(client, monkeypatch):
    monkeypatch.setattr(
        registry, "registry", registry.NotificationRegistry(hn.definitions())
    )
    token, admin, _ = account(client, privileges=("holds.administer", cfg.ADMIN))
    _, owner, _ = account(client, privileges=())
    _, contributor, _ = account(client, privileges=())
    with db() as c:
        # Baseline cases isolate responsible people; governor coverage is explicit below.
        c.execute("UPDATE roles SET is_information_governance=false WHERE is_information_governance")
        c.execute((ROOT / "database/seeds/hold-notification-producers.sql").read_text())
    assert len(run(admin, lambda c: configure(c, admin, "Legal governance"))) == 2
    return token, admin, owner, contributor


def create(client, enabled, **changes):
    token, admin, owner, contributor = enabled
    now = datetime.now(timezone.utc)
    data = dict(
        code="HN-" + uuid4().hex,
        name="CONFIDENTIAL CASE TITLE",
        owner_user_id=owner,
        contributor_user_ids=[contributor],
        valid_from=(now - timedelta(days=1)).isoformat(),
        valid_to=(now + timedelta(days=5)).isoformat(),
    )
    data.update(changes)
    response = client.post("/api/v1/holds", headers=_bearer(token), json=data)
    assert response.status_code == 201, response.text
    return response.json()


def messages(code):
    with db() as c:
        return c.execute(
            "SELECT * FROM message_envelopes WHERE system_producer_code=%s ORDER BY id",
            (code,),
        ).fetchall()


def patch(client, enabled, hold, **changes):
    return client.patch(
        f"/api/v1/holds/{hold['id']}",
        headers={
            **_bearer(enabled[0]),
            "If-Match": str(hold["version"]),
            "X-Change-Reason": "Approved lifecycle test",
        },
        json=changes,
    )


def test_assignment_creation_change_noop_localization_and_privacy(client, enabled):
    hold = create(client, enabled)
    assert len(messages(hn.ASSIGNED)) == 2
    with db() as c:
        recipients = c.execute(
            "SELECT recipient_user_id FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id WHERE e.system_producer_code=%s",
            (hn.ASSIGNED,),
        ).fetchall()
        assert {r["recipient_user_id"] for r in recipients} == set(enabled[2:])
        variants = c.execute("SELECT * FROM message_envelope_localizations").fetchall()
        assert any("تعليق قنوني" in r["subject"] for r in variants)
        assert all("CONFIDENTIAL" not in str(r) for r in variants)
        assert all(
            not r["action_required"] and not r["read_receipt_requested"]
            for r in messages(hn.ASSIGNED)
        )
    response = patch(client, enabled, hold, owner_user_id=enabled[2])
    assert response.status_code == 200, response.text
    assert len(messages(hn.ASSIGNED)) == 2
    response = patch(client, enabled, response.json(), owner_user_id=enabled[1])
    assert response.status_code == 200, response.text
    assert len(messages(hn.ASSIGNED)) == 3
    hold = response.json()
    r = client.put(
        f"/api/v1/holds/{hold['id']}/contributors",
        headers={
            **_bearer(enabled[0]),
            "If-Match": str(hold["version"]),
            "X-Change-Reason": "Assign contributor",
        },
        json={"user_ids": [enabled[3], enabled[2]]},
    )
    assert r.status_code == 200, r.text
    assert len(messages(hn.ASSIGNED)) == 4
    r = client.put(
        f"/api/v1/holds/{hold['id']}/contributors",
        headers={
            **_bearer(enabled[0]),
            "If-Match": str(r.json()["version"]),
            "X-Change-Reason": "Unchanged contributors",
        },
        json={"user_ids": [enabled[3], enabled[2]]},
    )
    assert r.status_code == 200, r.text
    assert len(messages(hn.ASSIGNED)) == 4


def test_reminder_once_per_end_date_current_audience_and_concurrent_workers(
    client, enabled
):
    hold = create(client, enabled)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: run(enabled[1], hn.process_reminders), range(2))
        )
    assert sum(results) == 1
    assert run(enabled[1], hn.process_reminders) == 0
    assert len(messages(hn.ENDING)) == 1
    response = patch(
        client,
        enabled,
        hold,
        valid_to=(datetime.now(timezone.utc) + timedelta(days=6)).isoformat(),
    )
    assert response.status_code == 200, response.text
    assert run(enabled[1], hn.process_reminders) == 1
    # Returning to an already-notified date does not create another reminder.
    response = patch(client, enabled, response.json(), valid_to=hold["valid_to"])
    assert response.status_code == 200, response.text
    assert run(enabled[1], hn.process_reminders) == 0
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM hold_notification_reminders"
            ).fetchone()["n"]
            == 2
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id WHERE e.system_producer_code=%s",
                (hn.ENDING,),
            ).fetchone()["n"]
            == 4
        )


def test_reminder_boundaries_no_inactive_recipients_and_bounded_batch(client, enabled):
    now = datetime.now(timezone.utc)
    create(client, enabled, valid_to=None)
    create(client, enabled, valid_to=(now - timedelta(hours=1)).isoformat())
    create(client, enabled, valid_from=(now + timedelta(days=1)).isoformat())
    create(client, enabled, valid_to=(now + timedelta(days=8)).isoformat())
    first = create(client, enabled)
    create(client, enabled)
    with db() as c:
        c.execute(
            "UPDATE users SET date_deactivated=CURRENT_TIMESTAMP WHERE id=%s",
            (enabled[3],),
        )
    assert run(enabled[1], lambda c: hn.process_reminders(c, limit=1)) == 1
    assert run(enabled[1], lambda c: hn.process_reminders(c, limit=1)) == 1
    assert run(enabled[1], hn.process_reminders) == 0
    with db() as c:
        recipients = c.execute(
            "SELECT recipient_user_id FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id WHERE e.system_producer_code=%s",
            (hn.ENDING,),
        ).fetchall()
        assert [r["recipient_user_id"] for r in recipients] == [enabled[2], enabled[2]]

    # Exact seven-day and exclusive-end boundaries in the worker's own transaction.
    def boundary(c):
        c.execute(
            "SELECT set_config('app.change_reason','Verify reminder boundaries',true)"
        )
        c.execute(
            "UPDATE holds SET valid_to=CURRENT_TIMESTAMP+interval '7 days' WHERE id=%s",
            (first["id"],),
        )
        assert hn.process_reminders(c) == 1
        c.execute(
            "UPDATE holds SET valid_to=CURRENT_TIMESTAMP WHERE id=%s", (first["id"],)
        )
        assert hn.process_reminders(c) == 0

    run(enabled[1], boundary)


def test_notification_failure_rolls_back_assignment_and_reminder(
    client, enabled, monkeypatch
):
    hold = create(client, enabled)
    before = len(messages(hn.ASSIGNED))
    original = hn.emit_system_notification

    def fail_after_write(**kwargs):
        original(**kwargs)
        raise HTTPException(409, detail="Injected notification failure")

    monkeypatch.setattr(hn, "emit_system_notification", fail_after_write)
    response = patch(client, enabled, hold, owner_user_id=enabled[1])
    assert response.status_code == 409
    with db() as c:
        assert (
            c.execute(
                "SELECT owner_user_id FROM holds WHERE id=%s", (hold["id"],)
            ).fetchone()["owner_user_id"]
            == enabled[2]
        )
    assert len(messages(hn.ASSIGNED)) == before
    with pytest.raises(HTTPException):
        run(enabled[1], hn.process_reminders)
    assert messages(hn.ENDING) == []
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM hold_notification_reminders"
            ).fetchone()["n"]
            == 0
        )


def test_disabled_producers_and_configuration_preservation(client, enabled):
    assert (
        run(enabled[1], lambda c: configure(c, enabled[1], "Do not replace existing"))
        == []
    )

    def disable(c):
        for code in (hn.ASSIGNED, hn.ENDING):
            state = cfg.state(c, code)
            row = cfg.load_version(c, code, state["active_configuration_version_id"])
            payload = cfg.configuration_from_row(row)
            payload.expected_version = state["latest_version"]
            payload.expected_active_configuration_version_id = state[
                "active_configuration_version_id"
            ]
            payload.enabled = False
            version = cfg.save(
                c, enabled[1], code, payload, "Disable approved optional producer"
            )
            cfg.activate(
                c,
                enabled[1],
                code,
                version["id"],
                cfg.Expected(
                    expected_version=version["version"],
                    expected_active_configuration_version_id=state[
                        "active_configuration_version_id"
                    ],
                ),
                "Disable approved optional producer",
            )

    run(enabled[1], disable)
    create(client, enabled)
    assert messages(hn.ASSIGNED) == []
    assert run(enabled[1], hn.process_reminders) == 0
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM event_history WHERE entity_type='system_notification' AND source='seeding'"
            ).fetchone()["n"]
            == 4
        )


def test_assignment_retry_uses_committed_event_and_reminder_current_members(
    client, enabled
):
    hold = create(client, enabled)
    assert len(messages(hn.ASSIGNED)) == 2
    run(
        enabled[1],
        lambda c: hn.notify_assignments(c, hold["id"], enabled[2:], enabled[1]),
    )
    assert len(messages(hn.ASSIGNED)) == 2
    # A changed owner and removal are resolved at reminder time, not creation time.
    changed = patch(client, enabled, hold, owner_user_id=enabled[1])
    assert changed.status_code == 200, changed.text
    response = client.put(
        f"/api/v1/holds/{hold['id']}/contributors",
        headers={
            **_bearer(enabled[0]),
            "If-Match": str(changed.json()["version"]),
            "X-Change-Reason": "Remove contributors",
        },
        json={"user_ids": []},
    )
    assert response.status_code == 200, response.text
    assert run(enabled[1], hn.process_reminders) == 1
    with db() as c:
        rows = c.execute(
            "SELECT recipient_user_id FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id WHERE e.system_producer_code=%s",
            (hn.ENDING,),
        ).fetchall()
        assert [r["recipient_user_id"] for r in rows] == [enabled[1]]


def test_inactive_audiences_do_not_starve_eligible_holds(client, enabled):
    hold = create(client, enabled)
    with db() as c:
        c.execute(
            "UPDATE users SET date_deactivated=CURRENT_TIMESTAMP WHERE id=ANY(%s)",
            (list(enabled[2:]),),
        )
    assert run(enabled[1], hn.process_reminders) == 0
    create(client, enabled, owner_user_id=enabled[1], contributor_user_ids=[])
    assert run(enabled[1], lambda c: hn.process_reminders(c, limit=1)) == 1
    with db() as c:
        assert not c.execute(
            "SELECT 1 FROM hold_notification_reminders WHERE hold_id=%s", (hold["id"],)
        ).fetchone()


def test_builtin_contracts_and_template_installation_require_authority(client, enabled):
    with pytest.raises(HTTPException) as denied:
        run(enabled[2], lambda c: configure(c, enabled[2], "Unauthorized installer"))
    assert denied.value.status_code == 403
    for definition in hn.definitions():
        assert not definition.required_for_business_commit
        assert definition.contract()["resource_link_kinds"] == []
        assert "static" not in definition.contract()["audience_modes"]
    with db() as c:
        assert registry.registry.reconcile(c)["ready"]
        assert cfg.readiness(c)["ready"]


def test_worker_leader_and_checkpoint_survive_notification_purge(client, enabled):
    from .test_messaging_phase5 import age
    from backend.services.api.messaging.retention import purge_group

    hold = create(client, enabled)
    with db() as leader:
        leader.execute("SELECT pg_advisory_xact_lock(482019038)")
        assert hn.reminder_tick() == 0
    assert hn.reminder_tick() == 1
    reminder = messages(hn.ENDING)[0]
    age([reminder["id"]], 40)
    with db() as c:
        assert purge_group(c, reminder["id"]) == 1
        assert c.execute(
            "SELECT 1 FROM hold_notification_reminders WHERE hold_id=%s", (hold["id"],)
        ).fetchone()
    assert messages(hn.ENDING) == []
    assert hn.reminder_tick() == 0


def test_localized_producer_names_search_fallback_and_seed_preservation(client, enabled):
    endpoint = '/api/v1/notification-administration/producers'
    headers = _bearer(enabled[0])
    def listing(q='', **params):
        r = client.get(endpoint, headers=headers, params={'q':q, **params})
        assert r.status_code == 200, r.text
        return r.json()
    english = listing('approaching expiry')['items']
    assert len(english) == 1
    assert english[0]['localized']['name'] == 'Legal hold approaching expiry'
    first = listing(limit=1)
    second = listing(limit=1, after=first['next_cursor'])
    assert first['items'][0]['producer_code'] != second['items'][0]['producer_code']
    with db() as c:
        c.execute("INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES(%s,'ar','UTC') ON CONFLICT(user_id) DO UPDATE SET language_tag='ar'", (enabled[1],))
    assert listing('اقتراب انتهاء')['items'][0]['localized']['name'] == 'اقتراب انتهاء تعليق قنوني'
    assert len(listing(hn.ASSIGNED)['items']) == 1
    detail = client.get(endpoint+'/'+hn.ASSIGNED, headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()['localized']['name'] == 'إسناد مسؤولية بشأن تعليق قنوني'
    with db() as c:
        c.execute("UPDATE system_notification_producers SET translations=NULL WHERE producer_code=%s", (hn.ENDING,))
    assert listing('expiry')['items'][0]['localized']['name'] == 'Legal hold approaching expiry'
    with db() as c:
        c.execute("UPDATE system_notification_producers SET translations=%s::jsonb WHERE producer_code=%s", ('{"ar":{"name":"صياغة محلية"}}', hn.ASSIGNED))
        c.execute((ROOT/'database/seeds/hold-notification-producers.sql').read_text())
    assert listing('صياغة محلية')['items'][0]['localized']['name'] == 'صياغة محلية'
    with db() as c:
        c.execute("UPDATE system_notification_producers SET translations=NULL WHERE producer_code=%s", (hn.ASSIGNED,))
        c.execute((ROOT/'database/seeds/hold-notification-producers.sql').read_text())


def test_information_governors_receive_expiry_only_and_effective_roles_only(client, enabled):
    _, governor, role = account(client, privileges=())
    _, expired, expired_role = account(client, privileges=())
    with db() as c:
        c.execute("UPDATE roles SET is_information_governance=true WHERE id IN (%s,%s)", (role, expired_role))
        c.execute("UPDATE user_role_assignments SET valid_until=CURRENT_TIMESTAMP WHERE user_id=%s", (expired,))
    hold = create(client, enabled)
    with db() as c:
        def recipients(code):
            return c.execute("SELECT d.recipient_user_id FROM message_deliveries d JOIN message_envelopes e ON e.id=d.envelope_id WHERE e.system_producer_code=%s", (code,)).fetchall()
        assigned = [r["recipient_user_id"] for r in recipients(hn.ASSIGNED)]
        assert governor not in assigned
        assert expired not in assigned
        assert set(assigned) == set(enabled[2:])
        # Governance alone never creates assignment eligibility.
        assert hn.assigned_audience(c, {"hold_id": hold["id"], "user_id": governor}) == []
        # A governor who is personally assigned still receives that assignment.
        c.execute("UPDATE roles SET is_information_governance=true WHERE id IN (SELECT role_id FROM user_role_assignments WHERE user_id=%s)", (enabled[2],))
        personal = hn.assigned_audience(c, {"hold_id": hold["id"], "user_id": enabled[2]})
        assert len(personal) == 1 and personal[0].target_id == enabled[2]
    assert run(enabled[1], hn.process_reminders) == 1
    with db() as c:
        ending = [r["recipient_user_id"] for r in recipients(hn.ENDING)]
        assert set(ending) == {governor, *enabled[2:]}
        assert len(ending) == len(set(ending))
        c.execute("UPDATE users SET date_deactivated=CURRENT_TIMESTAMP WHERE id IN (%s,%s)", enabled[2:])
    # Governors remain eligible even when there are no active responsible people.
    other = create(client, enabled, valid_to=(datetime.now(timezone.utc)+timedelta(days=6)).isoformat(), owner_user_id=enabled[1], contributor_user_ids=[])
    with db() as c:
        c.execute("UPDATE users SET date_deactivated=CURRENT_TIMESTAMP WHERE id=%s", (enabled[1],))
    assert run(governor, hn.process_reminders) == 1
    with db() as c:
        c.execute("UPDATE user_role_assignments SET valid_until=CURRENT_TIMESTAMP WHERE user_id=%s", (governor,))
        assert hn.ending_audience(c, {"hold_id": other["id"]}) == []
