from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def org_unit(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/org-units",
        json={"code": "LEGAL", "name": "Legal Affairs"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def user(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/users",
        json={
            "name": "محمد علي",
            "email": "person@example.test",
            "external_id": "HR-1001",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def role(client: TestClient, org_unit: dict) -> dict:
    response = client.post(
        "/api/v1/roles",
        json={
            "org_unit_id": org_unit["id"],
            "code": "LEGAL-MANAGER",
            "name": "Legal Affairs Manager",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_org_unit_crud_hierarchy_and_global_uniqueness(
    client: TestClient, org_unit: dict
):
    child_response = client.post(
        "/api/v1/org-units",
        json={
            "parent_org_unit_id": org_unit["id"],
            "code": "LEGAL-OPS",
            "name": "Legal Operations",
        },
    )
    assert child_response.status_code == 201
    child = child_response.json()

    duplicate = client.post(
        "/api/v1/org-units",
        json={"code": "legal", "name": "Different Name"},
    )
    assert duplicate.status_code == 409

    cycle = client.patch(
        f"/api/v1/org-units/{org_unit['id']}",
        json={"parent_org_unit_id": child["id"]},
        headers={"If-Match": str(org_unit["version"])},
    )
    assert cycle.status_code == 409

    listed = client.get(
        "/api/v1/org-units", params={"parent_org_unit_id": org_unit["id"]}
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [child["id"]]

    assert client.delete(f"/api/v1/org-units/{child['id']}", headers={"If-Match": str(child["version"])}).status_code == 405
    deactivated = client.post(
        f"/api/v1/org-units/{child['id']}/deactivate",
        headers={"If-Match": str(child["version"])},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"


def test_user_crud_neutral_name_and_explicit_lifecycle(client: TestClient, user: dict):
    assert user["name"] == "محمد علي"
    assert user["status"] == "active"

    response = client.post(
        f"/api/v1/users/{user['id']}/suspend",
        headers={"If-Match": str(user["version"])},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"

    bypass = client.patch(
        f"/api/v1/users/{user['id']}",
        json={"status": "active"},
        headers={"If-Match": str(response.json()["version"])},
    )
    assert bypass.status_code == 422

    duplicate_email = client.post(
        "/api/v1/users",
        json={"name": "Another Person", "email": "PERSON@example.test"},
    )
    assert duplicate_email.status_code == 409

    assert client.delete(f"/api/v1/users/{user['id']}", headers={"If-Match": str(response.json()["version"])}).status_code == 405
    deactivated = client.post(
        f"/api/v1/users/{user['id']}/deactivate",
        headers={"If-Match": str(response.json()["version"])},
    ).json()
    assert deactivated["status"] == "inactive"
    assert deactivated["date_deactivated"] is not None


def test_role_delete_is_not_exposed_before_permanent_deletion_is_implemented(
    client: TestClient, role: dict,
):
    response = client.delete(
        f"/api/v1/roles/{role['id']}",
        headers={"If-Match": str(role["version"])},
    )
    assert response.status_code == 405
    assert client.get(f"/api/v1/roles/{role['id']}").status_code == 200


def test_role_cross_unit_supervision_and_cycle_prevention(
    client: TestClient, org_unit: dict, role: dict
):
    other_unit = client.post(
        "/api/v1/org-units", json={"code": "FIN", "name": "Finance"}
    ).json()
    subordinate_response = client.post(
        "/api/v1/roles",
        json={
            "org_unit_id": other_unit["id"],
            "supervisor_role_id": role["id"],
            "code": "FIN-MANAGER",
            "name": "Finance Manager",
        },
    )
    assert subordinate_response.status_code == 201
    subordinate = subordinate_response.json()
    assert subordinate["org_unit_id"] != role["org_unit_id"]

    cycle = client.patch(
        f"/api/v1/roles/{role['id']}",
        json={"supervisor_role_id": subordinate["id"]},
        headers={"If-Match": str(role["version"])},
    )
    assert cycle.status_code == 409

    duplicate_name = client.post(
        "/api/v1/roles",
        json={
            "org_unit_id": other_unit["id"],
            "code": "ANOTHER-CODE",
            "name": "legal affairs manager",
        },
    )
    assert duplicate_name.status_code == 409


def test_temporal_role_assignment_and_navigation(
    client: TestClient, user: dict, role: dict
):
    response = client.post(
        "/api/v1/user-role-assignments",
        json={
            "user_id": user["id"],
            "role_id": role["id"],
            "valid_until": "2030-12-31T23:59:59Z",
        },
    )
    assert response.status_code == 201
    assignment = response.json()
    assert assignment["date_assigned"] == assignment["valid_from"]

    user_roles = client.get(f"/api/v1/users/{user['id']}/roles")
    role_users = client.get(f"/api/v1/roles/{role['id']}/users")
    assert [item["id"] for item in user_roles.json()] == [assignment["id"]]
    assert [item["id"] for item in role_users.json()] == [assignment["id"]]

    invalid_period = client.patch(
        f"/api/v1/user-role-assignments/{assignment['id']}",
        json={"valid_until": "2000-01-01T00:00:00Z"},
        headers={"If-Match": str(assignment["version"])},
    )
    assert invalid_period.status_code == 422

    assert client.delete(
        f"/api/v1/user-role-assignments/{assignment['id']}",
        headers={"If-Match": str(assignment["version"])},
    ).status_code == 204
    history = client.get(
        f"/api/v1/user-role-assignments/{assignment['id']}/history"
    ).json()
    assert [event["operation"] for event in history] == ["DELETE", "CREATE"]
    for event in history:
        parties = event["metadata"]["assignment_parties"]
        assert parties["user"] == {
            "id": user["id"],
            "name": "محمد علي",
            "email": "person@example.test",
        }
        assert parties["role"] == {
            "id": role["id"],
            "code": "LEGAL-MANAGER",
            "name": "Legal Affairs Manager",
        }


def test_user_management_search(client: TestClient, org_unit: dict, user: dict, role: dict):
    user_search = client.post(
        "/api/v1/users/search",
        json={
            "where": {
                "and": [
                    {"field": "name", "operator": "contains_ci", "value": "علي"},
                    {"field": "status", "operator": "eq", "value": "active"},
                ]
            }
        },
    )
    assert user_search.status_code == 200
    assert user_search.json()["total"] == 1

    role_search = client.post(
        "/api/v1/roles/search",
        json={
            "where": {
                "field": "org_unit_id",
                "operator": "eq",
                "value": org_unit["id"],
            }
        },
    )
    assert role_search.status_code == 200
    assert role_search.json()["items"][0]["id"] == role["id"]


def test_user_management_changes_are_audited(
    client: TestClient, org_unit: dict, user: dict, role: dict
):
    for path, entity_type, entity_id in (
        ("org-units", "org_unit", org_unit["id"]),
        ("users", "user", user["id"]),
        ("roles", "role", role["id"]),
    ):
        response = client.get(f"/api/v1/{path}/{entity_id}/history")
        assert response.status_code == 200
        assert response.json()[0]["entity_type"] == entity_type
        assert response.json()[0]["operation"] == "CREATE"


def test_org_unit_and_role_lifecycle_controls_effective_assignments(
    client: TestClient, org_unit: dict, user: dict, role: dict,
):
    child = client.post("/api/v1/org-units", json={
        "parent_org_unit_id": org_unit["id"], "code": "LEGAL-CHILD", "name": "Legal Child",
    }).json()
    child_role = client.post("/api/v1/roles", json={
        "org_unit_id": child["id"], "code": "LEGAL-CHILD-ROLE", "name": "Legal Child Role",
    }).json()

    inactive_unit = client.post(
        f"/api/v1/org-units/{org_unit['id']}/deactivate",
        headers={"If-Match": str(org_unit["version"])},
    )
    assert inactive_unit.status_code == 200, inactive_unit.text
    assert inactive_unit.json()["date_deactivated"] is not None
    blocked = client.post("/api/v1/user-role-assignments", json={
        "user_id": user["id"], "role_id": child_role["id"],
    })
    assert blocked.status_code == 409

    active_unit = client.post(
        f"/api/v1/org-units/{org_unit['id']}/activate",
        headers={"If-Match": str(inactive_unit.json()["version"])},
    )
    assert active_unit.status_code == 200
    assert active_unit.json()["date_deactivated"] is None
    assignment = client.post("/api/v1/user-role-assignments", json={
        "user_id": user["id"], "role_id": child_role["id"],
    })
    assert assignment.status_code == 201

    inactive_role = client.post(
        f"/api/v1/roles/{child_role['id']}/deactivate",
        headers={"If-Match": str(child_role["version"])},
    )
    assert inactive_role.status_code == 200
    assert client.get(f"/api/v1/users/{user['id']}").json()["status"] == "active"
    assert client.get(f"/api/v1/users/{user['id']}/roles").json()[0]["id"] == assignment.json()["id"]

    reactivated_role = client.post(
        f"/api/v1/roles/{child_role['id']}/activate",
        headers={"If-Match": str(inactive_role.json()["version"])},
    )
    assert reactivated_role.status_code == 200
    assert reactivated_role.json()["date_deactivated"] is None
