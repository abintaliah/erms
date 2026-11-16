"""Approved Phase 4 acceptance tests; disposable runner only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date
from uuid import uuid4
import pytest
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from .test_messaging import account, db, PREFIX
from .test_global_privilege_enforcement import _bearer
from backend.services.api.messaging import notification_registry as contracts
from backend.services.api.messaging.notification_registry import (
    SystemNotificationDefinition,
    NotificationRegistry,
    Placeholder,
)
from backend.services.api.messaging import notification_configuration as config
from backend.services.api.messaging.notifications import (
    emit_system_notification,
    emit_system_notification_test,
)
from backend.services.api.messaging.transactions import run

ADMIN = "/api/v1/notification-administration"


@pytest.fixture
def setup(client, monkeypatch):
    token, uid, _ = account(client, privileges=(config.ADMIN,))
    recipient, rid, _ = account(client, privileges=())
    definition = SystemNotificationDefinition(
        producer_code="test.phase4",
        feature_code="test",
        event_type="approved",
        contract_version=1,
        required_for_business_commit=True,
        placeholders={
            "name": Placeholder(type="text", max_length=80),
            "day": Placeholder(type="date"),
        },
        sample_context={"name": "Safe example", "day": "2026-10-03"},
    )
    monkeypatch.setattr(contracts, "registry", NotificationRegistry([definition]))
    with db() as c:
        c.execute("SELECT set_config('app.event_source','seeding',true)")
        c.execute(
            "INSERT INTO system_notification_producers(producer_code,feature_code,event_type,required_for_business_commit,contract_version,contract_definition) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                definition.producer_code,
                definition.feature_code,
                definition.event_type,
                True,
                1,
                Jsonb(definition.contract()),
            ),
        )
        langs = c.execute(
            "SELECT language_tag FROM supported_languages WHERE is_enabled OR language_tag='en'"
        ).fetchall()
    data = {
        "expected_version": 0,
        "expected_active_configuration_version_id": None,
        "enabled": True,
        "priority": "normal",
        "audience_mode": "static",
        "selectors": [{"selector_kind": "user", "target_id": rid}],
        "resource_presentation": {},
        "operational_owner": "Test team",
        "templates": [
            {
                "language_tag": r["language_tag"],
                "subject_template": "Notice {name}",
                "body_template_rich_text": "<p>{name}: {day}</p>",
                "review_status": "published",
            }
            for r in langs
        ],
    }
    return token, uid, recipient, rid, definition, data


def save_activate(client, setup, data=None):
    token, uid, recipient, rid, definition, initial = setup
    payload = data or initial
    saved = client.post(
        ADMIN + "/producers/" + definition.producer_code + "/versions",
        headers={**_bearer(token), "X-Change-Reason": "Approved fixture configuration"},
        json=payload,
    )
    assert saved.status_code == 200, saved.text
    version = saved.json()
    activated = client.post(
        ADMIN
        + "/producers/"
        + definition.producer_code
        + "/versions/"
        + version["id"]
        + "/activate",
        headers={**_bearer(token), "X-Change-Reason": "Activate reviewed fixture"},
        json={
            "expected_version": version["version"],
            "expected_active_configuration_version_id": payload[
                "expected_active_configuration_version_id"
            ],
        },
    )
    assert activated.status_code == 200, activated.text
    return version


def emit(uid, event="event-one", **changes):
    return run(
        uid,
        lambda c: emit_system_notification(
            transaction=c,
            producer_code="test.phase4",
            source_event_id=event,
            context={"name": "Alice", "day": date(2026, 10, 3)},
            triggered_by_user_id=uid,
            **changes,
        ),
    )


def test_registry_readiness_required_and_configuration_guards(client, setup):
    token, uid, _, rid, definition, data = setup
    with db() as c:
        assert not config.readiness(c)["ready"]
    assert client.get("/health").status_code == 503
    bad = {**data, "enabled": False}
    response = client.post(
        ADMIN + "/producers/test.phase4/versions",
        headers={**_bearer(token), "X-Change-Reason": "Cannot disable required"},
        json=bad,
    )
    assert response.status_code == 422
    save_activate(client, setup)
    assert client.get("/health").status_code == 200
    with pytest.raises(RuntimeError):
        NotificationRegistry([definition, definition])
    with db() as c:
        c.execute(
            "UPDATE system_notification_producers SET contract_version=2 WHERE producer_code='test.phase4'"
        )
    assert client.get("/health").status_code == 503
    with pytest.raises(HTTPException):
        emit(uid)


def test_atomic_system_send_immutable_variants_and_system_only_inbox(client, setup):
    token, uid, recipient, rid, definition, data = setup
    version = save_activate(client, setup)
    outcome = emit(uid)
    assert outcome.status == "created" and len(outcome.delivery_ids) == 1
    assert emit(uid).status == "existing"
    response = client.get(PREFIX + "/inbox", headers=_bearer(recipient))
    item = response.json()["items"][0]
    assert (
        item["sender_kind"] == "system"
        and not item["action_required"]
        and not item["read_receipt_requested"]
    )
    assert item["subject"] == "Notice Alice"
    assert client.get(PREFIX + "/outbox", headers=_bearer(recipient)).status_code == 403
    with db() as c:
        envelope = c.execute(
            "SELECT * FROM message_envelopes WHERE id=%s", (outcome.envelope_id,)
        ).fetchone()
        assert (
            envelope["security_level_id"]
            == c.execute(
                "SELECT id FROM security_levels ORDER BY level_number LIMIT 1"
            ).fetchone()["id"]
        )
        assert envelope["system_configuration_version_id"] == __import__("uuid").UUID(
            version["id"]
        )
        assert c.execute(
            "SELECT count(*) AS n FROM message_envelope_localizations WHERE envelope_id=%s",
            (outcome.envelope_id,),
        ).fetchone()["n"] == len(data["templates"])
    new = {
        **data,
        "expected_version": 1,
        "expected_active_configuration_version_id": version["id"],
        "templates": [
            {**t, "subject_template": "Changed {name}"} for t in data["templates"]
        ],
    }
    save_activate(client, setup, new)
    assert (
        client.get(
            PREFIX + "/inbox/" + str(outcome.delivery_ids[0]),
            headers=_bearer(recipient),
        ).json()["subject"]
        == "Notice Alice"
    )
    assert emit(uid).status == "existing"


def test_failure_rolls_back_business_change_and_notification(client, setup):
    _, uid, _, rid, _, _ = setup
    save_activate(client, setup)
    with pytest.raises(HTTPException):

        def business(c):
            c.execute("UPDATE users SET name='Should roll back' WHERE id=%s", (rid,))
            emit_system_notification(
                transaction=c,
                producer_code="test.phase4",
                source_event_id="bad",
                context={"name": "valid", "day": "not a date"},
                triggered_by_user_id=uid,
            )

        run(uid, business)
    with db() as c:
        assert (
            c.execute("SELECT name FROM users WHERE id=%s", (rid,)).fetchone()["name"]
            != "Should roll back"
        )
        assert (
            c.execute(
                "SELECT count(*) AS n FROM message_envelopes WHERE system_producer_code='test.phase4'"
            ).fetchone()["n"]
            == 0
        )
    with pytest.raises(RuntimeError):

        def business(c):
            emit_system_notification(
                transaction=c,
                producer_code="test.phase4",
                source_event_id="rollback",
                context={"name": "valid", "day": "2026-10-03"},
                triggered_by_user_id=uid,
            )
            raise RuntimeError("domain change failed")

        run(uid, business)
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM message_envelopes WHERE system_producer_code='test.phase4'"
            ).fetchone()["n"]
            == 0
        )


def test_optional_disable_and_context_authority(client, setup, monkeypatch):
    token, uid, _, rid, definition, data = setup
    from dataclasses import replace

    optional = replace(definition, required_for_business_commit=False)
    monkeypatch.setattr(contracts, "registry", NotificationRegistry([optional]))
    with db() as c:
        c.execute(
            "UPDATE system_notification_producers SET required_for_business_commit=false WHERE producer_code='test.phase4'"
        )
    save_activate(client, setup, {**data, "enabled": False})
    assert emit(uid).status == "disabled"
    with pytest.raises(TypeError):
        run(
            uid,
            lambda c: emit_system_notification(
                transaction=c,
                producer_code="test.phase4",
                source_event_id="x",
                context={},
                recipients=[rid],
            ),
        )
    with pytest.raises(HTTPException):
        run(
            uid,
            lambda c: emit_system_notification(
                transaction=c,
                producer_code="test.phase4",
                source_event_id="x",
                context={"name": "A", "day": "2026-10-03", "extra": "forbidden"},
            ),
        )


def test_templates_publication_concurrency_and_administration_boundaries(client, setup):
    token, uid, recipient, rid, definition, data = setup
    assert (
        client.get(ADMIN + "/producers", headers=_bearer(recipient)).status_code == 403
    )
    bad = {
        **data,
        "templates": [
            {**t, "subject_template": "{name.__class__}"} for t in data["templates"]
        ],
    }
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/preview",
            headers=_bearer(token),
            json={"configuration": bad, "context": definition.sample_context},
        ).status_code
        == 422
    )
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/versions", headers=_bearer(token), json=data
        ).status_code
        == 422
    )
    draft = {
        **data,
        "templates": [{**t, "review_status": "draft"} for t in data["templates"]],
    }
    saved = client.post(
        ADMIN + "/producers/test.phase4/versions",
        headers={**_bearer(token), "X-Change-Reason": "Draft"},
        json=draft,
    )
    assert saved.status_code == 200, saved.text
    identity = saved.json()["id"]
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/versions/" + identity + "/activate",
            headers={**_bearer(token), "X-Change-Reason": "Not reviewed"},
            json={"expected_version": 1},
        ).status_code
        == 409
    )
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/versions",
            headers={**_bearer(token), "X-Change-Reason": "Stale"},
            json=data,
        ).status_code
        == 409
    )
    assert client.post(
        PREFIX + "/system/send", headers=_bearer(token), json={}
    ).status_code in (404, 405)


def test_controlled_test_marking_limits_audit_and_retry(client, setup, monkeypatch):
    token, uid, recipient, rid, definition, data = setup
    version = save_activate(client, setup)
    payload = {
        "test_run_id": str(uuid4()),
        "configuration_version_id": version["id"],
        "recipient_user_ids": [rid],
        "context": definition.sample_context,
    }
    response = client.post(
        ADMIN + "/producers/test.phase4/test", headers=_bearer(token), json=payload
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/test", headers=_bearer(token), json=payload
        ).json()["status"]
        == "existing"
    )
    item = client.get(PREFIX + "/inbox", headers=_bearer(recipient)).json()["items"][0]
    assert item["is_test"] and item["subject"].startswith("TEST")
    with db() as c:
        row = c.execute(
            "SELECT * FROM message_envelopes WHERE id=%s",
            (response.json()["envelope_id"],),
        ).fetchone()
        assert (
            row["source_event_type"] == "test"
            and str(row["test_run_id"]) == payload["test_run_id"]
        )
        assert (row["expires_at"] - row["sent_at"]).days == 30
        assert row["test_initiated_by_user_id"] == uid
    history = client.get(
        ADMIN + "/producers/test.phase4/tests", headers=_bearer(token)
    ).json()["items"]
    assert len(history) == 1 and history[0]["metadata"]["is_test"]
    assert (
        "context" not in history[0]["metadata"]
        and "subject" not in history[0]["metadata"]
    )
    from backend.services.api.messaging.config import LIMITS

    monkeypatch.setitem(LIMITS, "TEST_SENDS_PER_HOUR", 1)
    response = client.post(
        ADMIN + "/producers/test.phase4/test",
        headers=_bearer(token),
        json={**payload, "test_run_id": str(uuid4())},
    )
    assert response.status_code == 429, response.text
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/test",
            headers=_bearer(token),
            json={**payload, "recipient_user_ids": [rid, rid]},
        ).status_code
        == 422
    )


def test_concurrent_event_retries_create_one_complete_fanout(client, setup):
    _, uid, _, _, _, _ = setup
    save_activate(client, setup)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: emit(uid, "concurrent"), range(4)))
    assert sum(o.status == "created" for o in outcomes) == 1
    assert len({o.envelope_id for o in outcomes}) == 1
    assert all(len(o.delivery_ids) == 1 for o in outcomes)


def test_language_variants_escape_values_and_preserve_send_language(client, setup):
    token, uid, recipient, rid, definition, data = setup
    data["templates"] = [
        {**t, "subject_template": t["language_tag"] + " {name}"}
        for t in data["templates"]
    ]
    save_activate(client, setup)
    with db() as c:
        c.execute(
            "INSERT INTO user_preferences(user_id,language_tag,working_timezone) VALUES (%s,'ar','UTC') ON CONFLICT(user_id) DO UPDATE SET language_tag='ar'",
            (rid,),
        )
    outcome = run(
        uid,
        lambda c: emit_system_notification(
            transaction=c,
            producer_code=definition.producer_code,
            source_event_id="escaped",
            context={"name": "<img src=x onerror=alert(1)>", "day": "2026-10-03"},
            triggered_by_user_id=uid,
        ),
    )
    with db() as c:
        c.execute(
            "UPDATE user_preferences SET language_tag='en' WHERE user_id=%s", (rid,)
        )
    row = client.get(PREFIX + "/inbox", headers=_bearer(recipient)).json()["items"][0]
    assert row["subject"].startswith("en ") and row["toast_subject"].startswith("ar ")
    assert row["toast_language_tag"] == "ar"
    with db() as c:
        variants = c.execute(
            "SELECT * FROM message_envelope_localizations WHERE envelope_id=%s",
            (outcome.envelope_id,),
        ).fetchall()
        assert all(
            "<img" not in v["body_rich_text"] and "&lt;img" in v["body_rich_text"]
            for v in variants
        )


def test_dynamic_audience_is_allowlisted_and_never_resolved_for_tests(
    client, setup, monkeypatch
):
    from dataclasses import replace

    token, uid, recipient, rid, definition, data = setup
    calls = []

    def resolve(c, context):
        calls.append(context)
        return [{"selector_kind": "user", "target_id": rid}]

    definition = replace(
        definition,
        allow_static_audience=False,
        audience_resolvers={"approved_recipients": resolve},
    )
    monkeypatch.setattr(contracts, "registry", NotificationRegistry([definition]))
    with db() as c:
        c.execute(
            "UPDATE system_notification_producers SET contract_definition=%s WHERE producer_code='test.phase4'",
            (Jsonb(definition.contract()),),
        )
    payload = {**data, "audience_mode": "approved_recipients", "selectors": []}
    version = save_activate(client, setup, payload)
    assert emit(uid).status == "created" and len(calls) == 1
    test = client.post(
        ADMIN + "/producers/test.phase4/test",
        headers=_bearer(token),
        json={
            "test_run_id": str(uuid4()),
            "configuration_version_id": version["id"],
            "recipient_user_ids": [uid],
            "context": definition.sample_context,
        },
    )
    assert test.status_code == 200, test.text
    assert len(calls) == 1
    with db() as c:
        assert (
            c.execute(
                "SELECT recipient_user_id FROM message_deliveries WHERE envelope_id=%s",
                (test.json()["envelope_id"],),
            ).fetchone()["recipient_user_id"]
            == uid
        )
    bad = {**payload, "audience_mode": "unregistered"}
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/preview",
            headers=_bearer(token),
            json={"configuration": bad, "context": definition.sample_context},
        ).status_code
        == 422
    )


def test_language_enablement_requires_published_active_variant(client, setup):
    token, uid, _, rid, _, data = setup
    version = save_activate(client, setup)
    language = {
        "language_tag": "fr",
        "english_name": "French",
        "native_name": "Français",
        "direction": "ltr",
        "is_enabled": True,
        "is_default": False,
        "formatting_config": {},
    }
    language_token, _, _ = account(client, privileges=("localization.administer",))
    response = client.post(
        "/api/v1/admin/i18n/languages",
        json=language,
        headers={**_bearer(language_token), "X-Change-Reason": "Test language guard"},
    )
    assert response.status_code == 409, response.text
    response = client.post(
        "/api/v1/admin/i18n/languages",
        json={**language, "is_enabled": False},
        headers={**_bearer(language_token), "X-Change-Reason": "Prepare language"},
    )
    assert response.status_code == 201, response.text
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        with db() as c:
            c.execute(
                "UPDATE supported_languages SET is_enabled=true WHERE language_tag='fr'"
            )
    updated = {
        **data,
        "expected_version": 1,
        "expected_active_configuration_version_id": version["id"],
        "templates": data["templates"]
        + [{**data["templates"][0], "language_tag": "fr"}],
    }
    save_activate(client, setup, updated)
    with db() as c:
        c.execute(
            "SELECT set_config('app.change_reason','Enable prepared language',true)"
        )
        c.execute(
            "UPDATE supported_languages SET is_enabled=true WHERE language_tag='fr'"
        )
    assert emit(uid).status == "created"
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM message_envelope_localizations WHERE language_tag='fr'"
            ).fetchone()["n"]
            == 1
        )


def test_template_parity_coverage_and_database_immutability(client, setup):
    import psycopg

    token, uid, _, _, definition, data = setup
    for bad in (
        {**data, "templates": [data["templates"][0]]},
        {
            **data,
            "templates": [
                (
                    {**t, "subject_template": "No placeholder"}
                    if t["language_tag"] == "ar"
                    else t
                )
                for t in data["templates"]
            ],
        },
        {
            **data,
            "templates": [
                {**t, "body_template_rich_text": "<p> </p>"} for t in data["templates"]
            ],
        },
    ):
        response = client.post(
            ADMIN + "/producers/test.phase4/versions",
            headers={**_bearer(token), "X-Change-Reason": "Invalid templates"},
            json=bad,
        )
        assert response.status_code == 422, response.text
    version = save_activate(client, setup)
    for table, column in [
        ("system_notification_configuration_versions", "operational_owner"),
        ("system_notification_configuration_translations", "subject_template"),
    ]:
        with pytest.raises(psycopg.Error):
            with db() as c:
                c.execute(f"UPDATE {table} SET {column}='Forbidden mutation'")
    outcome = emit(uid)
    with pytest.raises(psycopg.Error):
        with db() as c:
            c.execute(
                "UPDATE message_envelopes SET is_test=true WHERE id=%s",
                (outcome.envelope_id,),
            )


def test_test_send_ignores_stale_static_audience_and_pending_draft_is_valid(
    client, setup
):
    token, uid, _, rid, definition, data = setup
    response = client.post(
        ADMIN + "/producers/test.phase4/versions",
        headers={**_bearer(token), "X-Change-Reason": "Pending draft"},
        json={
            **data,
            "templates": [{**t, "review_status": "draft"} for t in data["templates"]],
        },
    )
    assert response.status_code == 200, response.text
    with db() as c:
        c.execute(
            "UPDATE users SET date_deactivated=CURRENT_TIMESTAMP WHERE id=%s", (rid,)
        )
    payload = {
        "test_run_id": str(uuid4()),
        "configuration_version_id": response.json()["id"],
        "recipient_user_ids": [uid],
        "context": definition.sample_context,
    }
    response = client.post(
        ADMIN + "/producers/test.phase4/test", headers=_bearer(token), json=payload
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            ADMIN + "/producers/test.phase4/test",
            headers=_bearer(token),
            json={
                **payload,
                "test_run_id": str(uuid4()),
                "recipient_user_ids": list(range(1, 12)),
            },
        ).status_code
        == 422
    )
    with db() as c:
        envelope = c.execute(
            "SELECT * FROM message_envelopes WHERE id=%s",
            (response.json()["envelope_id"],),
        ).fetchone()
        assert (
            not envelope["read_receipt_requested"]
            and not envelope["action_required"]
            and envelope["action_due_at"] is None
        )


def test_resource_builder_cannot_bypass_baseline_or_authorization(
    client, record, setup, monkeypatch
):
    from dataclasses import replace
    from pydantic import BaseModel, ConfigDict

    token, uid, _, rid, definition, data = setup

    class Presentation(BaseModel):
        model_config = ConfigDict(extra="forbid")
        include_record: bool = True

    definition = replace(
        definition,
        resource_link_kinds=("record",),
        resource_configuration=Presentation,
        resource_builder=lambda c, context, presentation: [
            {
                "resource_kind": "record",
                "target_id": record["id"],
                "link_token": str(uuid4()),
            }
        ],
    )
    monkeypatch.setattr(contracts, "registry", NotificationRegistry([definition]))
    with db() as c:
        c.execute(
            "UPDATE system_notification_producers SET contract_definition=%s WHERE producer_code='test.phase4'",
            (Jsonb(definition.contract()),),
        )
    save_activate(client, setup)
    with pytest.raises(HTTPException):
        emit(uid, "denied")
    assert emit(1, "allowed").status == "created"
    with db() as c:
        c.execute(
            "UPDATE roles SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=1"
        )
        c.execute(
            "UPDATE aggregations SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=%s",
            (record["aggregation_id"],),
        )
        c.execute(
            "UPDATE records SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=%s",
            (record["id"],),
        )
    with pytest.raises(HTTPException) as error:
        emit(1, "above-baseline")
    assert error.value.detail["code"] == "message_resource_level_too_high"
    with db() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM message_envelopes WHERE system_producer_code='test.phase4'"
            ).fetchone()["n"]
            == 1
        )


def test_typed_context_rejects_coercion_nonfinite_and_oversized_values():
    definition = SystemNotificationDefinition(
        "test.types",
        "test",
        "typed",
        1,
        False,
        placeholders={"value": Placeholder(type="decimal")},
    )
    for value in ("not a number", "NaN", "Infinity", True):
        with pytest.raises(HTTPException):
            contracts.validate_context(definition, {"value": value})
    from dataclasses import replace

    definition = replace(
        definition, placeholders={"value": Placeholder(type="text", max_length=4)}
    )
    with pytest.raises(HTTPException):
        contracts.validate_context(definition, {"value": "a     "})


def test_registry_unknown_and_missing_required_contracts_fail_closed(client, setup):
    _, _, _, _, definition, _ = setup
    with db() as c:
        assert NotificationRegistry().reconcile(c)["issues"] == [
            {
                "producer_code": "test.phase4",
                "code": "unknown_database_contract",
                "required": True,
            }
        ]
        c.execute(
            "DELETE FROM system_notification_producers WHERE producer_code='test.phase4'"
        )
        result = NotificationRegistry([definition]).reconcile(c)
        assert (
            not result["ready"]
            and result["issues"][0]["code"] == "missing_database_contract"
        )
        assert not c.execute(
            "SELECT 1 FROM system_notification_producers WHERE producer_code='test.phase4'"
        ).fetchone()


def test_language_activation_race_preserves_coverage(client, setup):
    import threading
    import psycopg

    token, uid, _, _, _, data = setup
    old = save_activate(client, setup)
    with db() as c:
        c.execute(
            "SELECT set_config('app.change_reason','Prepare future language',true)"
        )
        c.execute(
            "INSERT INTO supported_languages(language_tag,english_name,native_name,direction,is_enabled,formatting_config) VALUES ('fr','French','Français','ltr',false,'{}')"
        )
    new = save_activate(
        client,
        setup,
        {
            **data,
            "expected_version": 1,
            "expected_active_configuration_version_id": old["id"],
            "templates": data["templates"]
            + [{**data["templates"][0], "language_tag": "fr"}],
        },
    )
    ready = threading.Event()
    release = threading.Event()

    def activate_old_snapshot():
        with db() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            c.execute("SELECT count(*) FROM supported_languages")
            ready.set()
            assert release.wait(10)
            try:
                config.activate(
                    c,
                    uid,
                    "test.phase4",
                    old["id"],
                    config.Expected(
                        expected_version=2,
                        expected_active_configuration_version_id=new["id"],
                    ),
                    "Race activation",
                )
            except psycopg.errors.SerializationFailure:
                return "retry"
            except HTTPException:
                return "rejected"
            return "activated"

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(activate_old_snapshot)
        assert ready.wait(10)
        try:
            with db() as c:
                c.execute(
                    "SELECT set_config('app.change_reason','Enable covered language',true)"
                )
                c.execute(
                    "UPDATE supported_languages SET is_enabled=true WHERE language_tag='fr'"
                )
        finally:
            release.set()
        assert pending.result() in ("retry", "rejected")
    with db() as c:
        assert config.coverage(c, config.load_version(c, "test.phase4", new["id"]))


def test_internal_service_requires_existing_transaction(client, setup):
    with db() as c:
        with pytest.raises(RuntimeError):
            emit_system_notification(
                transaction=c,
                producer_code="test.phase4",
                source_event_id="idle",
                context={},
            )


def test_test_send_rate_is_atomic_and_system_messages_cannot_be_reused(
    client, setup, monkeypatch
):
    from backend.services.api.messaging.config import LIMITS
    from .test_messaging import payload as human_payload, EXCHANGE

    token, uid, _, _, definition, _ = setup
    version = save_activate(client, setup)
    recipient, rid, _ = account(client, privileges=(EXCHANGE,))
    monkeypatch.setitem(LIMITS, "TEST_SENDS_PER_HOUR", 1)

    def attempt(_):
        try:
            return run(
                uid,
                lambda c: emit_system_notification_test(
                    transaction=c,
                    producer_code="test.phase4",
                    configuration_version_id=__import__("uuid").UUID(version["id"]),
                    test_run_id=uuid4(),
                    context=definition.sample_context,
                    recipient_user_ids=[rid],
                    initiated_by_user_id=uid,
                ),
            )
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert results.count(429) == 1
    result = next(r for r in results if r != 429)
    for relationship in ("reply", "forward"):
        response = client.post(
            PREFIX + "/send",
            headers=_bearer(recipient),
            json=human_payload(
                rid,
                relationship_kind=relationship,
                related_delivery_id=str(result.delivery_ids[0]),
            ),
        )
        assert response.status_code == 422, response.text
    response = client.post(
        ADMIN + "/producers/test.phase4/test",
        headers=_bearer(token),
        json={
            "test_run_id": str(uuid4()),
            "configuration_version_id": version["id"],
            "context": definition.sample_context,
            "recipient_user_ids": [rid],
            "action_required": True,
        },
    )
    assert response.status_code == 422


def test_static_role_overlap_deduplicates_to_precedence_without_exchange(client, setup):
    token, uid, _, rid, _, data = setup
    with db() as c:
        role = c.execute(
            "SELECT role_id FROM user_role_assignments WHERE user_id=%s", (rid,)
        ).fetchone()["role_id"]
    save_activate(
        client,
        setup,
        {
            **data,
            "selectors": [
                {"selector_kind": "role", "target_id": role, "recipient_type": "cc"},
                {"selector_kind": "user", "target_id": rid, "recipient_type": "to"},
            ],
        },
    )
    outcome = emit(uid)
    assert len(outcome.delivery_ids) == 1
    with db() as c:
        assert (
            c.execute(
                "SELECT recipient_type FROM message_deliveries WHERE id=%s",
                (outcome.delivery_ids[0],),
            ).fetchone()["recipient_type"]
            == "to"
        )
