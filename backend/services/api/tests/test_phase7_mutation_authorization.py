import os
from datetime import datetime, timezone

import psycopg
from fastapi.testclient import TestClient

from backend.services.api.authentication import hash_password


PASSWORD = "Phase-7-Test-Password-123!"


def _grant_principal(
    privilege_codes: set[str], *, clearance_code: str = "TS",
) -> tuple[int, int]:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("DELETE FROM profiles WHERE code='phase-7'")
        profile_id = connection.execute(
            "INSERT INTO profiles(code,name) VALUES ('phase-7','Phase 7') RETURNING id"
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO profile_privileges(profile_id,privilege_id)
               SELECT %s,id FROM privileges WHERE code=ANY(%s)""",
            (profile_id, list(privilege_codes)),
        )
        level_id = connection.execute(
            "SELECT id FROM security_levels WHERE code=%s", (clearance_code,),
        ).fetchone()[0]
        role_id = connection.execute(
            """INSERT INTO roles(org_unit_id,code,name,profile_id,security_level_id)
               VALUES (1,'phase-7-role','Phase 7 role',%s,%s) RETURNING id""",
            (profile_id, level_id),
        ).fetchone()[0]
        user_id = connection.execute(
            "INSERT INTO users(name,email) VALUES ('Phase Seven','phase7@test.invalid') RETURNING id"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_role_assignments(user_id,role_id) VALUES (%s,%s)",
            (user_id, role_id),
        )
        connection.execute(
            "INSERT INTO user_credentials(user_id,password_hash,must_change_password) VALUES (%s,%s,false)",
            (user_id, hash_password(PASSWORD)),
        )
    return user_id, role_id


def _set_aggregation_acl(aggregation_id: int, role_id: int, permissions: set[str]) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "UPDATE aggregations SET inherit_acl_from_parent=false WHERE id=%s AND parent_aggregation_id IS NOT NULL",
            (aggregation_id,),
        )
        connection.execute(
            "DELETE FROM aggregation_acl_grants WHERE aggregation_id=%s", (aggregation_id,),
        )
        connection.execute(
            """INSERT INTO aggregation_acl_grants(
                   aggregation_id,principal_type,role_id,permission_id
               ) SELECT %s,'role',%s,id FROM permissions
                 WHERE resource_type='aggregation' AND code=ANY(%s)""",
            (aggregation_id, role_id, list(permissions)),
        )


def _set_record_acl(record_id: int, role_id: int, permissions: set[str]) -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE records SET inherit_acl_from_parent=false WHERE id=%s", (record_id,))
        connection.execute("DELETE FROM record_acl_grants WHERE record_id=%s", (record_id,))
        connection.execute(
            """INSERT INTO record_acl_grants(record_id,principal_type,role_id,permission_id)
               SELECT %s,'role',%s,id FROM permissions
               WHERE resource_type='record' AND code=ANY(%s)""",
            (record_id, role_id, list(permissions)),
        )


def _login_as_phase7(client: TestClient) -> None:
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "phase7@test.invalid", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")


def test_aggregation_metadata_requires_matching_global_and_acl_grants(
    client: TestClient, aggregation: dict,
):
    user_id, role_id = _grant_principal({"aggregation.view", "aggregation.modify"})
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.modify_metadata"},
    )
    _login_as_phase7(client)

    capabilities = client.get(
        f"/api/v1/aggregations/{aggregation['id']}/capabilities"
    ).json()["capabilities"]
    assert capabilities["modify_metadata"] is True
    assert capabilities["delete"] is False
    response = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"title": "Authorized title"},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert response.status_code == 200, response.text
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        event = connection.execute(
            """SELECT operation,actor_user_id FROM event_history
               WHERE entity_type='aggregation' AND entity_id=%s
               ORDER BY id DESC LIMIT 1""",
            (aggregation["id"],),
        ).fetchone()
    assert event == ("UPDATE", user_id)


def test_global_privilege_does_not_replace_resource_permission(
    client: TestClient, aggregation: dict,
):
    _, role_id = _grant_principal({"aggregation.view", "aggregation.modify"})
    _set_aggregation_acl(aggregation["id"], role_id, {"aggregation.view"})
    _login_as_phase7(client)
    response = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"title": "Must not change"},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "insufficient_resource_permission"


def test_aggregation_move_requires_source_and_destination_permissions_and_rolls_back(
    client: TestClient, aggregation: dict,
):
    source = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": aggregation["id"],
        "aggregation_number": "SOURCE-CHILD", "title": "Source child",
    }).json()
    destination = client.post("/api/v1/aggregations", json={
        "aggregation_number": "DEST", "title": "Destination", "classification_id": 1,
    }).json()
    _, role_id = _grant_principal({"aggregation.view", "aggregation.move"})
    _set_aggregation_acl(
        source["id"], role_id, {"aggregation.view", "aggregation.move"},
    )
    _set_aggregation_acl(destination["id"], role_id, {"aggregation.view"})
    _login_as_phase7(client)
    current_source = client.get(f"/api/v1/aggregations/{source['id']}").json()

    denied = client.patch(
        f"/api/v1/aggregations/{source['id']}",
        json={"parent_aggregation_id": destination["id"]},
        headers={"If-Match": str(current_source["version"])},
    )
    assert denied.status_code == 403
    assert client.get(f"/api/v1/aggregations/{source['id']}").json()["parent_aggregation_id"] == aggregation["id"]

    _set_aggregation_acl(
        destination["id"], role_id,
        {"aggregation.view", "aggregation.receive_child"},
    )
    moved = client.patch(
        f"/api/v1/aggregations/{source['id']}",
        json={"parent_aggregation_id": destination["id"]},
        headers={"If-Match": str(current_source["version"])},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["parent_aggregation_id"] == destination["id"]


def test_close_is_independent_of_metadata_modify_permission(
    client: TestClient, aggregation: dict,
):
    _, role_id = _grant_principal({"aggregation.view", "aggregation.close"})
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.close"},
    )
    _login_as_phase7(client)
    closed = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"date_closed": aggregation["date_created"]},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert closed.status_code == 200, closed.text
    denied_reopen = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"date_closed": None},
        headers={"If-Match": str(closed.json()["version"])},
    )
    assert denied_reopen.status_code == 403


def test_close_before_opening_returns_accessible_validation_error(
    client: TestClient, aggregation: dict,
):
    future_opened = datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1)
    updated = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"date_opened": future_opened.isoformat()},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert updated.status_code == 200, updated.text
    _, role_id = _grant_principal({"aggregation.view", "aggregation.close"})
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.close"},
    )
    _login_as_phase7(client)

    denied = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"date_closed": datetime.now(timezone.utc).isoformat()},
        headers={"If-Match": str(updated.json()["version"])},
    )
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "closure_before_opening"
    assert "cannot be closed before its opening date" in denied.json()["detail"]["message"]


def test_record_move_requires_both_sides(
    client: TestClient, aggregation: dict, record: dict,
):
    destination = client.post("/api/v1/aggregations", json={
        "aggregation_number": "REC-DEST", "title": "Record destination",
        "classification_id": 1,
    }).json()
    _, role_id = _grant_principal({"aggregation.view", "record.view", "record.move"})
    _set_record_acl(record["id"], role_id, {"record.view", "record.move"})
    _set_aggregation_acl(destination["id"], role_id, {"aggregation.view"})
    _login_as_phase7(client)
    current_record = client.get(f"/api/v1/records/{record['id']}").json()
    denied = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"aggregation_id": destination["id"]},
        headers={"If-Match": str(current_record["version"])},
    )
    assert denied.status_code == 403
    _set_aggregation_acl(
        destination["id"], role_id,
        {"aggregation.view", "aggregation.receive_record"},
    )
    moved = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"aggregation_id": destination["id"]},
        headers={"If-Match": str(current_record["version"])},
    )
    assert moved.status_code == 200, moved.text


def test_stale_mutation_is_atomic_and_does_not_overwrite(
    client: TestClient, aggregation: dict,
):
    _, role_id = _grant_principal({"aggregation.view", "aggregation.modify"})
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.modify_metadata"},
    )
    _login_as_phase7(client)
    first = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}", json={"title": "First"},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert first.status_code == 200
    stale = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}", json={"title": "Stale"},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert stale.status_code == 412
    assert client.get(f"/api/v1/aggregations/{aggregation['id']}").json()["title"] == "First"


def test_clearance_boundary_conceals_resource_even_with_privilege_and_acl(
    client: TestClient, aggregation: dict,
):
    _, role_id = _grant_principal({"aggregation.view", "aggregation.modify"}, clearance_code="G")
    _set_aggregation_acl(
        aggregation["id"], role_id, {"aggregation.view", "aggregation.modify_metadata"},
    )
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "UPDATE aggregations SET security_level_id=(SELECT id FROM security_levels WHERE code='S') WHERE id=%s",
            (aggregation["id"],),
        )
    _login_as_phase7(client)
    assert client.get(f"/api/v1/aggregations/{aggregation['id']}").status_code == 404
    denied = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}", json={"title": "Hidden"},
        headers={"If-Match": str(aggregation["version"] + 1)},
    )
    assert denied.status_code == 404
