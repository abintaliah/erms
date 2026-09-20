import os

import psycopg
from fastapi.testclient import TestClient

from backend.services.api.governance_authorization import OPERATION_POLICY
from backend.services.api.tests.test_phase7_mutation_authorization import (
    PASSWORD, _grant_principal, _login_as_phase7,
)
from frontend.webui.authorization_ui import OPERATIONS


def test_explanation_operation_policy_maps_every_ui_operation_to_the_correct_requirements():
    assert OPERATION_POLICY == {
        "aggregation.view": ("aggregation.view", "aggregation.view"),
        "aggregation.modify_metadata": ("aggregation.modify", "aggregation.modify_metadata"),
        "aggregation.delete": ("aggregation.delete", "aggregation.delete"),
        "aggregation.close": ("aggregation.close", "aggregation.close"),
        "aggregation.reopen": ("aggregation.reopen", "aggregation.reopen"),
        "aggregation.move": ("aggregation.move", "aggregation.move"),
        "aggregation.reclassify": ("aggregation.reclassify", "aggregation.reclassify"),
        "aggregation.security_level.change": (
            "aggregation.security_level.change", "aggregation.security_level.change",
        ),
        "aggregation.acl.manage": ("aggregation.acl.manage", "aggregation.acl.manage"),
        "aggregation.add_child": ("aggregation.create_child", "aggregation.add_child"),
        "aggregation.add_record": ("record.create", "aggregation.add_record"),
        "record.view": ("record.view", "record.view"),
        "record.modify_metadata": ("record.modify", "record.modify_metadata"),
        "record.delete": ("record.delete", "record.delete"),
        "record.move": ("record.move", "record.move"),
        "record.security_level.change": (
            "record.security_level.change", "record.security_level.change",
        ),
        "record.acl.manage": ("record.acl.manage", "record.acl.manage"),
        "record.component.list": ("record.view", "record.component.list"),
        "record.component.view": ("record.component.view", "record.component.view"),
        "record.component.download": (
            "record.component.download", "record.component.download",
        ),
        "record.component.add": ("record.component.add", "record.component.add"),
        "record.component.replace": (
            "record.component.replace", "record.component.replace",
        ),
        "record.component.remove": ("record.component.remove", "record.component.remove"),
        "record.component.reorder": (
            "record.component.reorder", "record.component.reorder",
        ),
    }
    assert set(OPERATIONS["aggregation"] + OPERATIONS["record"]) == set(OPERATION_POLICY)


def _login_admin(client: TestClient) -> None:
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    response = client.post("/api/v1/auth/login", json={
        "email": "admin@test.invalid", "password": "Temporary-Test-Password-123!",
    })
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")


def _governance(role_id: int, value: bool = True) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "UPDATE roles SET is_information_governance=%s WHERE id=%s", (value, role_id),
        )


def _empty_record_acl(record_id: int) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE records SET inherit_acl_from_parent=false WHERE id=%s", (record_id,))
        connection.execute("DELETE FROM record_acl_grants WHERE record_id=%s", (record_id,))


def test_governance_bypasses_acl_only_and_records_qualifying_role(
    client: TestClient, record: dict,
):
    _, role_id = _grant_principal({"record.view", "record.modify"})
    _governance(role_id)
    _empty_record_acl(record["id"])
    _login_as_phase7(client)
    current = client.get(f"/api/v1/records/{record['id']}")
    assert current.status_code == 200
    changed = client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "Governed correction"},
        headers={"If-Match": str(current.json()["version"])},
    )
    assert changed.status_code == 200, changed.text
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        event = connection.execute(
            """SELECT metadata FROM event_history WHERE entity_type='record' AND entity_id=%s
               AND operation='INFORMATION_GOVERNANCE_BYPASS_USED'
               ORDER BY id DESC LIMIT 1""", (record["id"],),
        ).fetchone()
    assert event[0]["authorization_basis"] == "information_governance"
    assert event[0]["required_permission"] == "record.modify_metadata"
    assert event[0]["qualifying_roles"][0]["id"] == role_id


def test_high_clearance_non_governance_role_cannot_lend_clearance_to_governance_role(
    client: TestClient, aggregation: dict, record: dict,
):
    user_id, low_governance_role = _grant_principal(
        {"record.view", "record.modify"}, clearance_code="G",
    )
    _governance(low_governance_role)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        top_level = connection.execute("SELECT id FROM security_levels WHERE code='TS'").fetchone()[0]
        secret_level = connection.execute("SELECT id FROM security_levels WHERE code='S'").fetchone()[0]
        profile_id = connection.execute(
            "SELECT profile_id FROM roles WHERE id=%s", (low_governance_role,),
        ).fetchone()[0]
        high_role = connection.execute(
            """INSERT INTO roles(org_unit_id,code,name,profile_id,security_level_id)
               VALUES (1,'phase-9-high','High non-governance',%s,%s) RETURNING id""",
            (profile_id, top_level),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
            (user_id, high_role),
        )
        connection.execute(
            "UPDATE aggregations SET security_level_id=%s WHERE id=%s",
            (secret_level, aggregation["id"]),
        )
        connection.execute(
            "UPDATE records SET security_level_id=%s,inherit_acl_from_parent=false WHERE id=%s",
            (secret_level, record["id"]),
        )
        connection.execute("DELETE FROM record_acl_grants WHERE record_id=%s", (record["id"],))
    _login_as_phase7(client)
    assert client.get(f"/api/v1/records/{record['id']}").status_code == 404


def test_governance_does_not_supply_missing_global_or_unrelated_administration(
    client: TestClient, record: dict,
):
    _, role_id = _grant_principal({"record.view"})
    _governance(role_id)
    _empty_record_acl(record["id"])
    _login_as_phase7(client)
    current = client.get(f"/api/v1/records/{record['id']}").json()
    denied = client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "No privilege"},
        headers={"If-Match": str(current["version"])},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "insufficient_privilege"
    assert client.get("/api/v1/users/1/deletion-preflight").status_code == 403


def test_access_explanation_supports_self_and_audited_other_user_diagnosis(
    client: TestClient, record: dict,
):
    user_id, role_id = _grant_principal({"record.view"})
    _governance(role_id)
    _empty_record_acl(record["id"])
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            """INSERT INTO record_acl_grants(record_id,principal_type,role_id,permission_id)
               SELECT %s,'role',1,id FROM permissions WHERE code='record.view'""",
            (record["id"],),
        )
    _login_as_phase7(client)
    own = client.post("/api/v1/authorization/explain", json={
        "resource_type": "record", "resource_id": record["id"], "operation": "record.view",
    })
    assert own.status_code == 200, own.text
    assert own.json()["allowed"] is True
    assert own.json()["contributors"]["governance_bypass_role_ids"] == [role_id]
    assert set(own.json()["effective_security_level"]) == {
        "id", "code", "name", "level_number",
    }
    assert set(own.json()["required_security_level"]) == {
        "id", "code", "name", "level_number",
    }
    assert own.json()["required_security_level"]["level_number"] == own.json()["required_clearance"]

    _login_admin(client)
    other = client.post("/api/v1/authorization/explain", json={
        "resource_type": "record", "resource_id": record["id"],
        "operation": "record.modify_metadata", "user_id": user_id,
    })
    assert other.status_code == 200, other.text
    assert other.json()["other_user_diagnostic"] is True
    assert other.json()["allowed"] is False
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        assert connection.execute(
            """SELECT 1 FROM event_history WHERE entity_type='record' AND entity_id=%s
               AND operation='ACCESS_EXPLANATION_VIEWED'""", (record["id"],),
        ).fetchone()


def test_explainable_user_picker_is_minimal_and_requires_explanation_privilege(
    client: TestClient,
):
    _login_admin(client)
    response = client.get("/api/v1/authorization/explainable-users")
    assert response.status_code == 200
    assert response.json()
    assert set(response.json()[0]) == {"id", "name", "email", "status"}

    _grant_principal({"record.view"})
    _login_as_phase7(client)
    assert client.get("/api/v1/authorization/explainable-users").status_code == 403


def test_governance_custody_view_exposes_assignments_and_resilience_warning(
    client: TestClient,
):
    user_id, role_id = _grant_principal({"record.view"})
    _governance(role_id)
    _login_admin(client)
    response = client.get("/api/v1/authorization/governance-custody")
    assert response.status_code == 200, response.text
    body = response.json()
    role = next(role for role in body["governance_roles"] if role["id"] == role_id)
    assert role["profile_code"]
    assert role["is_highest_clearance"] is True
    assert role["qualifies_for_universal_custody"] is False
    assert role["missing_custody_privilege_codes"]
    assignment = next(
        item for item in body["assignments"]
        if item["user_id"] == user_id and item["role_id"] == role_id
    )
    assert assignment["effective_for_universal_custody"] is False
    assert "role_not_universal_custody_qualified" in assignment["ineffective_reasons"]
    assert body["highest_security_level"]["level_number"] == max(
        level["level_number"] for level in body["security_levels"]
    )
    assert "authorization.administer" in body["required_custody_privilege_codes"]
    assert body["warnings"][0]["code"] == "zero_universal_governance_custodians"


def test_governance_explanation_and_operation_preserve_closure_integrity(
    client: TestClient, aggregation: dict, record: dict,
):
    _, role_id = _grant_principal({"record.view", "record.modify"})
    _governance(role_id)
    _empty_record_acl(record["id"])
    closed = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"date_closed": aggregation["date_created"]},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert closed.status_code == 200
    _login_as_phase7(client)
    explanation = client.post("/api/v1/authorization/explain", json={
        "resource_type": "record", "resource_id": record["id"],
        "operation": "record.modify_metadata",
    })
    assert explanation.status_code == 200
    assert explanation.json()["allowed"] is False
    assert explanation.json()["decision_code"] == "operation_not_allowed"
    current = client.get(f"/api/v1/records/{record['id']}").json()
    assert client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "Still frozen"},
        headers={"If-Match": str(current["version"])},
    ).status_code == 409
