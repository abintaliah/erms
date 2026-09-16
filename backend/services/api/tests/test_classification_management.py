from fastapi.testclient import TestClient


def create_scheme(client: TestClient, code: str = "CORP") -> dict:
    response = client.post("/api/v1/classification-schemes", json={
        "code": code, "title": f"{code} File Plan", "authority": "Records Office",
    })
    assert response.status_code == 201, response.text
    scheme = response.json()
    published = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/publish",
        headers={"If-Match": str(scheme["version"])},
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_hierarchy_inheritance_assignment_and_local_override(client: TestClient):
    scheme = create_scheme(client)
    branch_response = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "FIN", "title": "Finance",
        "retention_rule": {
            "current_period_years": 3, "intermediate_period_years": 4,
            "final_disposition": "destruction", "instructions": "Destroy after review",
        },
    })
    assert branch_response.status_code == 201, branch_response.text
    branch = branch_response.json()
    terminal_response = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"],
        "parent_classification_id": branch["id"], "code": "FIN-AP",
        "title": "Accounts payable", "description": "Supplier invoices", "is_terminal": True,
    })
    assert terminal_response.status_code == 201, terminal_response.text
    terminal = terminal_response.json()

    effective = client.get(f"/api/v1/classifications/{terminal['id']}/effective-retention-rule")
    assert effective.status_code == 200
    assert effective.json()["defined_by_classification_id"] == branch["id"]
    assert effective.json()["inheritance_depth"] == 1

    root_response = client.post("/api/v1/aggregations", json={
        "aggregation_number": "FIN-2026", "title": "Finance 2026",
        "classification_id": terminal["id"],
    })
    assert root_response.status_code == 201, root_response.text
    root = root_response.json()
    child_response = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": root["id"], "aggregation_number": "FIN-2026-01",
        "title": "January",
    })
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()

    inherited_response = client.get(f"/api/v1/aggregations/{child['id']}/effective-retention-rule")
    assert inherited_response.status_code == 200, inherited_response.text
    inherited = inherited_response.json()
    assert inherited["governing_root_aggregation_id"] == root["id"]
    assert inherited["rule_source"] == "classification"

    override = client.put(
        f"/api/v1/aggregations/{root['id']}/retention-rule",
        headers={"X-Change-Reason": "Legal hold extension"},
        json={
            "current_period_years": 10, "intermediate_period_years": 2,
            "final_disposition": "retain_as_local_archives",
            "instructions": "Retain locally", "justification": "Legal hold extension",
        },
    )
    assert override.status_code == 200, override.text
    governed = client.get(f"/api/v1/aggregations/{child['id']}/effective-retention-rule").json()
    assert governed["rule_source"] == "aggregation"
    assert governed["current_period_years"] == 10
    assert client.put(
        f"/api/v1/aggregations/{child['id']}/retention-rule",
        headers={"X-Change-Reason": "Not permitted"},
        json={
            "current_period_years": 1, "intermediate_period_years": 1,
            "final_disposition": "destruction", "justification": "Not permitted",
        },
    ).status_code == 409


def test_scheme_lifecycle_search_wildcards_and_recent_selections(client: TestClient):
    scheme = create_scheme(client, "OPS")
    terminal = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "OPS-CASE",
        "title": "Operational Cases", "description": "Daily case work", "is_terminal": True,
        "retention_rule": {
            "current_period_years": 2, "intermediate_period_years": 1,
            "final_disposition": "selective_preservation",
        },
    }).json()
    found = client.post("/api/v1/classifications/search", json={
        "where": {"field": "title", "operator": "matches_ci", "value": "oper*case?"}
    })
    assert found.status_code == 200, found.text
    assert [item["id"] for item in found.json()["items"]] == [terminal["id"]]

    created = client.post("/api/v1/aggregations", json={
        "aggregation_number": "OPS-ROOT", "title": "Operations", "classification_id": terminal["id"],
    })
    assert created.status_code == 201, created.text
    recent = client.get("/api/v1/classifications/recent")
    assert recent.status_code == 200
    assert [item["id"] for item in recent.json()] == [terminal["id"]]

    deactivated = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/deactivate",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Superseded"},
    )
    assert deactivated.status_code == 200, deactivated.text
    rejected = client.post("/api/v1/aggregations", json={
        "aggregation_number": "OPS-NEW", "title": "Rejected", "classification_id": terminal["id"],
    })
    assert rejected.status_code == 409
    assert client.get("/api/v1/classifications/recent").json() == []


def test_database_rejects_terminal_without_effective_rule(client: TestClient):
    scheme = create_scheme(client, "EMPTY")
    response = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "EMPTY-01",
        "title": "Invalid terminal", "is_terminal": True,
    })
    assert response.status_code == 409
