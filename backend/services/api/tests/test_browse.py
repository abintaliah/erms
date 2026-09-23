from fastapi.testclient import TestClient


def _published_scheme(client: TestClient, code: str = "BROWSE") -> dict:
    scheme = client.post("/api/v1/classification-schemes", json={
        "code": code, "title": f"{code} Scheme",
    }).json()
    response = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/publish",
        headers={"If-Match": str(scheme["version"])},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _classification(
    client: TestClient, scheme_id: int, code: str, *, parent_id: int | None = None,
    terminal: bool = False,
) -> dict:
    payload = {
        "classification_scheme_id": scheme_id,
        "parent_classification_id": parent_id,
        "code": code,
        "title": f"Classification {code}",
        "is_terminal": terminal,
    }
    if terminal:
        payload["retention_rule"] = {
            "current_period_years": 5,
            "intermediate_period_years": 0,
            "final_disposition": "destruction",
        }
    response = client.post("/api/v1/classifications", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_browse_hierarchy_returns_counts_and_direct_relationships(client: TestClient):
    scheme = _published_scheme(client)
    branch = _classification(client, scheme["id"], "B-01")
    terminal = _classification(
        client, scheme["id"], "B-01.01", parent_id=branch["id"], terminal=True,
    )
    root = client.post("/api/v1/aggregations", json={
        "classification_id": terminal["id"],
        "aggregation_number": "AG-01", "title": "Root aggregation",
    }).json()
    child = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": root["id"],
        "aggregation_number": "AG-01.01", "title": "Child aggregation",
    }).json()
    record = client.post("/api/v1/records", json={
        "aggregation_id": root["id"], "record_number": "REC-01",
        "title": "Browse record",
    }).json()

    roots = client.get(f"/api/v1/browse/classification-schemes/{scheme['id']}/roots")
    assert roots.status_code == 200, roots.text
    assert roots.json()["items"][0]["child_classification_count"] == 1

    children = client.get(f"/api/v1/browse/classifications/{branch['id']}/children")
    assert children.status_code == 200, children.text
    assert children.json()["items"][0]["root_aggregation_count"] == 1

    governed = client.get(f"/api/v1/browse/classifications/{terminal['id']}/aggregations")
    assert governed.status_code == 200, governed.text
    assert governed.json()["items"][0]["child_aggregation_count"] == 1
    assert governed.json()["items"][0]["record_count"] == 1

    aggregation_children = client.get(f"/api/v1/browse/aggregations/{root['id']}/children")
    assert [item["id"] for item in aggregation_children.json()["items"]] == [child["id"]]
    records = client.get(f"/api/v1/browse/aggregations/{root['id']}/records")
    assert [item["id"] for item in records.json()["items"]] == [record["id"]]


def test_browse_cursor_is_stable_and_scoped(client: TestClient):
    scheme = _published_scheme(client)
    terminal = _classification(client, scheme["id"], "PAGE", terminal=True)
    for number in ("AG-10", "AG-02", "AG-01"):
        response = client.post("/api/v1/aggregations", json={
            "classification_id": terminal["id"],
            "aggregation_number": number, "title": number,
        })
        assert response.status_code == 201, response.text

    first = client.get(
        f"/api/v1/browse/classifications/{terminal['id']}/aggregations",
        params={"limit": 2},
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert [item["aggregation_number"] for item in body["items"]] == ["AG-01", "AG-02"]
    assert body["total"] == 3
    assert body["next_cursor"]

    second = client.get(
        f"/api/v1/browse/classifications/{terminal['id']}/aggregations",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert [item["aggregation_number"] for item in second.json()["items"]] == ["AG-10"]
    assert second.json()["next_cursor"] is None

    mismatch = client.get(
        f"/api/v1/browse/classifications/{terminal['id']}/aggregations",
        params={"cursor": body["next_cursor"], "query": "different"},
    )
    assert mismatch.status_code == 400


def test_browse_filters_immediate_collection_and_rejects_branch_aggregations(client: TestClient):
    scheme = _published_scheme(client)
    branch = _classification(client, scheme["id"], "FILTER")
    terminal = _classification(
        client, scheme["id"], "FILTER.01", parent_id=branch["id"], terminal=True,
    )
    for number, title in (("A-01", "Annual accounts"), ("B-01", "Service contracts")):
        client.post("/api/v1/aggregations", json={
            "classification_id": terminal["id"],
            "aggregation_number": number, "title": title,
        })

    filtered = client.get(
        f"/api/v1/browse/classifications/{terminal['id']}/aggregations",
        params={"query": "contract"},
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["aggregation_number"] == "B-01"

    rejected = client.get(f"/api/v1/browse/classifications/{branch['id']}/aggregations")
    assert rejected.status_code == 409


def test_organization_browser_is_lazy_bounded_and_reports_assignment_context(client: TestClient):
    root = client.post("/api/v1/org-units", json={"code": "OB", "name": "Organization Browser"}).json()
    child = client.post("/api/v1/org-units", json={
        "parent_org_unit_id": root["id"], "code": "OB-C", "name": "Child Unit",
    }).json()
    role = client.post("/api/v1/roles", json={
        "org_unit_id": child["id"], "code": "OB-R", "name": "Browser Role",
    }).json()
    person = client.post("/api/v1/users", json={
        "name": "Browse Person", "email": "browse.person@example.test",
        "account_type": "person",
    }).json()
    assignment = client.post("/api/v1/user-role-assignments", json={
        "user_id": person["id"], "role_id": role["id"],
    }).json()

    roots = client.get("/api/v1/browse/organization/roots")
    assert roots.status_code == 200, roots.text
    root_node = next(item for item in roots.json() if item["id"] == root["id"])
    assert root_node["child_org_unit_count"] == 1
    assert "roles" not in root_node

    root_children = client.get(
        f"/api/v1/browse/organization/org-units/{root['id']}/children"
    )
    assert [item["id"] for item in root_children.json()["org_units"]] == [child["id"]]
    assert root_children.json()["roles"] == []

    child_children = client.get(
        f"/api/v1/browse/organization/org-units/{child['id']}/children"
    )
    assert [item["id"] for item in child_children.json()["roles"]] == [role["id"]]

    child_summary = client.get(
        f"/api/v1/browse/organization/org-units/{child['id']}/summary"
    )
    assert child_summary.status_code == 200, child_summary.text
    assert child_summary.json()["ancestors"] == [{
        "id": root["id"], "code": "OB", "name": "Organization Browser",
    }]
    assert child_summary.json()["holdings_metrics"] == {
        "aggregation_count": 0,
        "open_aggregation_count": 0,
        "closed_aggregation_count": 0,
        "physical_aggregation_count": 0,
        "digital_aggregation_count": 0,
        "mixed_aggregation_count": 0,
        "record_count": 0,
        "physical_record_count": 0,
        "digital_record_count": 0,
        "mixed_record_count": 0,
        "vital_record_count": 0,
        "storage_size_in_bytes": 0,
    }

    users = client.get(f"/api/v1/browse/organization/roles/{role['id']}/users")
    assert users.status_code == 200, users.text
    assert users.json()[0]["id"] == person["id"]
    assert users.json()[0]["assignment_id"] == assignment["id"]
    assert users.json()[0]["assignment_validity"] == "current"

    role_summary = client.get(f"/api/v1/browse/organization/roles/{role['id']}/summary")
    assert role_summary.json()["assigned_user_count"] == 1
    assert role_summary.json()["current_assignment_count"] == 1
    assert role_summary.json()["profile_privileges"]
    assert {
        "code", "name", "description", "category", "is_reserved",
    } <= role_summary.json()["profile_privileges"][0].keys()

    found = client.get("/api/v1/browse/organization/search", params={"query": "Browse Person"})
    user_result = next(
        item for item in found.json()
        if item["type"] == "user" and item["id"] == person["id"]
    )
    assert user_result["org_unit_path"] == [root["id"], child["id"]]
    assert user_result["role_id"] == role["id"]

    role_result = client.get(
        "/api/v1/browse/organization/search",
        params={"query": "Browser Role", "entity_type": "role", "status": "active"},
    ).json()[0]
    assert role_result["org_unit_path"] == [root["id"], child["id"]]

    hidden = client.get(
        "/api/v1/browse/organization/search",
        params={"query": "Browser Role", "entity_type": "role", "status": "inactive"},
    )
    assert hidden.status_code == 200
    assert hidden.json() == []


def test_organization_unit_selector_mode_can_omit_roles(client: TestClient):
    unit = client.post("/api/v1/org-units", json={"code": "SEL", "name": "Selector Unit"}).json()
    client.post("/api/v1/roles", json={
        "org_unit_id": unit["id"], "code": "SEL-R", "name": "Hidden Role",
    })
    response = client.get(
        f"/api/v1/browse/organization/org-units/{unit['id']}/children",
        params={"include_roles": False},
    )
    assert response.status_code == 200
    assert response.json()["roles"] == []
