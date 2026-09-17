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


def test_scheme_list_supports_controlled_sorting(client: TestClient):
    zebra = client.post("/api/v1/classification-schemes", json={
        "code": "Z-01", "title": "Alpha scheme", "authority": "Records Office",
    }).json()
    alpha = client.post("/api/v1/classification-schemes", json={
        "code": "A-01", "title": "Zulu scheme", "authority": "Records Office",
    }).json()
    published = client.post(
        f"/api/v1/classification-schemes/{alpha['id']}/publish",
        headers={"If-Match": str(alpha["version"])},
    ).json()
    client.post(
        f"/api/v1/classification-schemes/{zebra['id']}/deactivate",
        headers={"If-Match": str(zebra["version"]), "X-Change-Reason": "Test ordering"},
    )

    by_title = client.get(
        "/api/v1/classification-schemes", params={"sort": "title", "direction": "asc"},
    )
    assert by_title.status_code == 200, by_title.text
    assert [row["title"] for row in by_title.json()] == [
        "Alpha scheme", "Test Scheme", "Zulu scheme",
    ]

    by_code = client.get(
        "/api/v1/classification-schemes", params={"sort": "code", "direction": "desc"},
    )
    assert by_code.status_code == 200, by_code.text
    assert [row["code"] for row in by_code.json()] == ["Z-01", "TEST", "A-01"]

    by_status = client.get(
        "/api/v1/classification-schemes",
        params={"sort": "published_status", "direction": "asc"},
    )
    assert by_status.status_code == 200, by_status.text
    status_rows = by_status.json()
    assert status_rows[-1]["id"] == zebra["id"]
    assert next(index for index, row in enumerate(status_rows) if row["id"] == published["id"]) < len(status_rows) - 1

    invalid = client.get("/api/v1/classification-schemes", params={"sort": "authority"})
    assert invalid.status_code == 422


def test_scheme_classification_counts_are_aggregated_in_one_request(client: TestClient):
    scheme = client.post("/api/v1/classification-schemes", json={
        "code": "COUNTS", "title": "Counted Scheme",
    }).json()
    branch = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "COUNTS-01",
        "title": "Counted branch", "retention_rule": {
            "current_period_years": 1, "intermediate_period_years": 0,
            "final_disposition": "destruction",
        },
    }).json()
    client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"],
        "parent_classification_id": branch["id"], "code": "COUNTS-01.01",
        "title": "Counted terminal", "is_terminal": True,
    })

    response = client.get("/api/v1/classification-schemes/classification-counts")
    assert response.status_code == 200, response.text
    counted = next(row for row in response.json() if row["classification_scheme_id"] == scheme["id"])
    assert counted == {
        "classification_scheme_id": scheme["id"],
        "branch_count": 1,
        "terminal_count": 1,
    }


def test_unused_unpublished_scheme_bulk_deletion_is_audited(client: TestClient):
    scheme = client.post("/api/v1/classification-schemes", json={
        "code": "ABANDONED", "title": "Abandoned Draft Scheme",
    }).json()
    branch = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "A",
        "title": "Draft branch", "retention_rule": {
            "current_period_years": 1, "intermediate_period_years": 0,
            "final_disposition": "destruction",
        },
    }).json()
    terminal = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"],
        "parent_classification_id": branch["id"], "code": "A-01",
        "title": "Draft terminal", "is_terminal": True,
    })
    assert terminal.status_code == 201, terminal.text

    deleted = client.delete(
        f"/api/v1/classification-schemes/{scheme['id']}",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Abandoned draft"},
    )
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/classification-schemes/{scheme['id']}").status_code == 404
    events = client.post("/api/v1/event-history/search", json={
        "where": {"and": [
            {"field": "entity_type", "operator": "eq", "value": "classification_scheme"},
            {"field": "entity_id", "operator": "eq", "value": scheme["id"]},
        ]},
    }).json()["items"]
    assert any(
        event["operation"] == "DELETE" and event["reason"] == "Abandoned draft"
        for event in events
    )


def test_accidental_publication_can_be_reversed_before_first_use(client: TestClient):
    scheme = create_scheme(client, "ACCIDENT")
    blocked = client.delete(
        f"/api/v1/classification-schemes/{scheme['id']}",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Published accidentally"},
    )
    assert blocked.status_code == 409
    unpublished = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/unpublish",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Published accidentally"},
    )
    assert unpublished.status_code == 200, unpublished.text
    result = unpublished.json()
    assert result["date_published"] is None
    assert result["date_first_used"] is None
    deleted = client.delete(
        f"/api/v1/classification-schemes/{scheme['id']}",
        headers={"If-Match": str(result["version"]), "X-Change-Reason": "Discard unused scheme"},
    )
    assert deleted.status_code == 204, deleted.text


def test_scheme_cannot_be_unpublished_or_deleted_after_first_use(client: TestClient):
    scheme = create_scheme(client, "USED")
    terminal = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "USED-01",
        "title": "Used classification", "is_terminal": True,
        "retention_rule": {
            "current_period_years": 1, "intermediate_period_years": 0,
            "final_disposition": "destruction",
        },
    }).json()
    created = client.post("/api/v1/aggregations", json={
        "aggregation_number": "USED-AGG", "title": "Governed aggregation",
        "classification_id": terminal["id"],
    })
    assert created.status_code == 201, created.text
    refreshed = client.get(f"/api/v1/classification-schemes/{scheme['id']}").json()
    assert refreshed["date_first_used"] is not None
    unpublished = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/unpublish",
        headers={"If-Match": str(refreshed["version"]), "X-Change-Reason": "Should fail"},
    )
    assert unpublished.status_code == 409
    assert "governed an aggregation" in unpublished.json()["detail"]
    deleted = client.delete(
        f"/api/v1/classification-schemes/{scheme['id']}",
        headers={"If-Match": str(refreshed["version"]), "X-Change-Reason": "Should fail"},
    )
    assert deleted.status_code == 409


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

    scheme = client.get(f"/api/v1/classification-schemes/{scheme['id']}").json()
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


def test_classification_deletion_requires_draft_active_unused_leaf_and_reason(client: TestClient):
    scheme = client.post("/api/v1/classification-schemes", json={
        "code": "DELETE-C", "title": "Classification deletion",
    }).json()
    branch = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "DEL",
        "title": "Parent branch", "retention_rule": {
            "current_period_years": 1, "intermediate_period_years": 0,
            "final_disposition": "destruction",
        },
    }).json()
    leaf = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"],
        "parent_classification_id": branch["id"], "code": "DEL-01",
        "title": "Unused leaf", "is_terminal": True,
    }).json()

    assert client.delete(
        f"/api/v1/classifications/{leaf['id']}",
        headers={"If-Match": str(leaf["version"])},
    ).status_code == 422
    assert client.delete(
        f"/api/v1/classifications/{branch['id']}",
        headers={"If-Match": str(branch["version"]), "X-Change-Reason": "Remove draft"},
    ).status_code == 409
    deleted = client.delete(
        f"/api/v1/classifications/{leaf['id']}",
        headers={"If-Match": str(leaf["version"]), "X-Change-Reason": "Remove draft leaf"},
    )
    assert deleted.status_code == 204, deleted.text

    branch = client.get(f"/api/v1/classifications/{branch['id']}").json()
    deactivated_scheme = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/deactivate",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Pause draft"},
    )
    assert deactivated_scheme.status_code == 200
    blocked = client.delete(
        f"/api/v1/classifications/{branch['id']}",
        headers={"If-Match": str(branch["version"]), "X-Change-Reason": "Should fail"},
    )
    assert blocked.status_code == 409
    assert "scheme is deactivated" in blocked.json()["detail"]


def test_classification_deletion_allowed_after_publish_then_unpublish(client: TestClient):
    scheme = create_scheme(client, "PUBLISH-UNDO")
    leaf = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "PU-01",
        "title": "Mistaken publication leaf", "is_terminal": True,
        "retention_rule": {
            "current_period_years": 1, "intermediate_period_years": 0,
            "final_disposition": "destruction",
        },
    }).json()
    assert client.delete(
        f"/api/v1/classifications/{leaf['id']}",
        headers={"If-Match": str(leaf["version"]), "X-Change-Reason": "Should fail"},
    ).status_code == 409
    scheme = client.post(
        f"/api/v1/classification-schemes/{scheme['id']}/unpublish",
        headers={"If-Match": str(scheme["version"]), "X-Change-Reason": "Published by mistake"},
    ).json()
    deleted = client.delete(
        f"/api/v1/classifications/{leaf['id']}",
        headers={"If-Match": str(leaf["version"]), "X-Change-Reason": "Discard unused leaf"},
    )
    assert deleted.status_code == 204, deleted.text


def test_classification_first_use_and_inherited_deactivation(client: TestClient):
    scheme = create_scheme(client, "LIFECYCLE")
    branch = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"], "code": "LIFE",
        "title": "Lifecycle branch", "retention_rule": {
            "current_period_years": 5, "intermediate_period_years": 1,
            "final_disposition": "destruction",
        },
    }).json()
    terminal = client.post("/api/v1/classifications", json={
        "classification_scheme_id": scheme["id"],
        "parent_classification_id": branch["id"], "code": "LIFE-01",
        "title": "Lifecycle terminal", "is_terminal": True,
    }).json()
    aggregation = client.post("/api/v1/aggregations", json={
        "aggregation_number": "LIFE-AGG", "title": "Existing governed aggregation",
        "classification_id": terminal["id"],
    })
    assert aggregation.status_code == 201, aggregation.text

    branch = client.get(f"/api/v1/classifications/{branch['id']}").json()
    terminal = client.get(f"/api/v1/classifications/{terminal['id']}").json()
    assert branch["date_first_used"] is not None
    assert terminal["date_first_used"] is not None

    deactivated = client.post(
        f"/api/v1/classifications/{branch['id']}/deactivate",
        headers={"If-Match": str(branch["version"]), "X-Change-Reason": "No new files"},
    )
    assert deactivated.status_code == 200, deactivated.text
    eligible = client.get(
        "/api/v1/classifications",
        params={"classification_scheme_id": scheme["id"], "eligible": True},
    )
    assert terminal["id"] not in [row["id"] for row in eligible.json()]
    existing_rule = client.get(
        f"/api/v1/aggregations/{aggregation.json()['id']}/effective-retention-rule"
    )
    assert existing_rule.status_code == 200

    branch = deactivated.json()
    reactivated = client.post(
        f"/api/v1/classifications/{branch['id']}/reactivate",
        headers={"If-Match": str(branch["version"]), "X-Change-Reason": "Resume filing"},
    )
    assert reactivated.status_code == 200, reactivated.text
    eligible = client.get(
        "/api/v1/classifications",
        params={"classification_scheme_id": scheme["id"], "eligible": True},
    )
    assert terminal["id"] in [row["id"] for row in eligible.json()]
