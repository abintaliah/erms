import json
import os
import time

import psycopg
from psycopg.rows import dict_row

from backend.services.api.tests.test_global_privilege_enforcement import _account, _bearer
from backend.services.api.tests.test_phase9_governance_authorization import _login_admin


def test_security_dashboard_aggregates_denials_without_protected_content(client):
    token, _, _ = _account(client, privileges=(), suffix="phase11-denial")
    denied = client.get("/api/v1/users/1/deletion-preflight", headers=_bearer(token))
    assert denied.status_code == 403

    _login_admin(client)
    response = client.get("/api/v1/security-operations/summary?hours=24")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_privilege_roles"]
    assert all(
        set(role) == {
            "id", "code", "name", "status", "profile_code", "profile_name",
            "is_builtin_bootstrap_profile",
        }
        for role in body["full_privilege_roles"]
    )
    assert body["total_denials"] >= 1
    group = next(item for item in body["denial_groups"]
                 if item["required_privilege"] == "identity.users.administer")
    assert group["decision_code"] == "insufficient_privilege"
    serialized = json.dumps(body)
    assert token not in serialized
    assert "before_state" not in serialized and "after_state" not in serialized
    assert all(
        not item["entity_label"].startswith("User #")
        for item in body["recent_events"]
        if item["entity_type"] == "user" and not item["redacted"]
    )


def test_security_dashboard_warns_for_custom_profile_with_every_privilege(client):
    _login_admin(client)
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        profile_id = connection.execute(
            """INSERT INTO profiles(code,name,description)
               VALUES ('CUSTOM-UNRESTRICTED','Custom unrestricted','Test profile')
               RETURNING id"""
        ).fetchone()["id"]
        connection.execute(
            """INSERT INTO profile_privileges(profile_id,privilege_id)
               SELECT %s,id FROM privileges""",
            (profile_id,),
        )
        org_unit_id = connection.execute(
            "SELECT id FROM org_units ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        security_level_id = connection.execute(
            "SELECT id FROM security_levels ORDER BY level_number LIMIT 1"
        ).fetchone()["id"]
        role_id = connection.execute(
            """INSERT INTO roles(org_unit_id,code,name,profile_id,security_level_id)
               VALUES (%s,'CUSTOM-ALL','Custom all privileges',%s,%s) RETURNING id""",
            (org_unit_id, profile_id, security_level_id),
        ).fetchone()["id"]

    response = client.get("/api/v1/security-operations/summary?hours=24")
    assert response.status_code == 200, response.text
    warning = next(
        role for role in response.json()["full_privilege_roles"] if role["id"] == role_id
    )
    assert warning["profile_code"] == "CUSTOM-UNRESTRICTED"
    assert warning["is_builtin_bootstrap_profile"] is False

    references = client.get("/api/v1/profiles/reference?limit=500")
    assert references.status_code == 200, references.text
    reference = next(item for item in references.json() if item["id"] == profile_id)
    assert reference["grants_all_privileges"] is True


def test_reconciliation_reports_administrators_custodians_and_hierarchy(client):
    response = client.get("/api/v1/security-operations/reconciliation")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_authorization_administrators"]
    assert body["hierarchy_violation_count"] == 0
    assert body["ownership_invariant_violation_count"] == 0
    assert body["ownership_invariant_violations_by_type"] == {}
    assert all(set(item) >= {"code", "severity"} for item in body["findings"])


def test_security_monitoring_index_and_latency_budget(client):
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        index = connection.execute(
            """SELECT indexdef FROM pg_indexes
               WHERE indexname='event_history_security_operation_timeline_idx'"""
        ).fetchone()
    assert index and "operation" in index["indexdef"] and "occurred_at" in index["indexdef"]

    started = time.perf_counter()
    for _ in range(25):
        response = client.get("/api/v1/security-operations/summary?hours=24")
        assert response.status_code == 200
    assert time.perf_counter() - started < 5.0


def test_denial_actor_snapshot_survives_later_identity_rename(client):
    token, user_id, _ = _account(client, privileges=(), suffix="phase11-snapshot")
    assert client.get("/api/v1/users/1/deletion-preflight", headers=_bearer(token)).status_code == 403
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        before = connection.execute(
            """SELECT actor_name,actor_email FROM event_history
               WHERE entity_type='user' AND entity_id=%s AND operation='AUTHORIZATION_DENIED'
               ORDER BY id DESC LIMIT 1""", (user_id,),
        ).fetchone()
        connection.execute(
            "UPDATE users SET name='Renamed after event',email='renamed-after-event@test.invalid' WHERE id=%s",
            (user_id,),
        )
        after = connection.execute(
            """SELECT actor_name,actor_email FROM event_history
               WHERE entity_type='user' AND entity_id=%s AND operation='AUTHORIZATION_DENIED'
               ORDER BY id DESC LIMIT 1""", (user_id,),
        ).fetchone()
    assert before == after
    assert after["actor_name"] != "Renamed after event"
