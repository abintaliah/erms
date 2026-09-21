from fastapi.testclient import TestClient


def test_resource_responses_and_filters_expose_organizational_owner(
    client: TestClient,
):
    root_response = client.post(
        "/api/v1/aggregations",
        json={
            "aggregation_number": "OWN-001",
            "title": "Organizational holdings",
            "classification_id": 1,
        },
    )
    assert root_response.status_code == 201, root_response.text
    root = root_response.json()
    assert root["owning_org_unit_id"] == 1
    assert root["owning_org_unit_code"] == "test-root"
    assert root["owning_org_unit_name"] == "Test Root"

    child_response = client.post(
        "/api/v1/aggregations",
        json={
            "parent_aggregation_id": root["id"],
            "aggregation_number": "OWN-001-01",
            "title": "Child holdings",
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()
    assert child["owning_org_unit_id"] == root["owning_org_unit_id"]
    assert child["owning_org_unit_name"] == "Test Root"

    record_response = client.post(
        "/api/v1/records",
        json={
            "aggregation_id": child["id"],
            "record_number": "OWN-REC-001",
            "title": "Owned record",
        },
    )
    assert record_response.status_code == 201, record_response.text
    record = record_response.json()
    assert record["owning_org_unit_id"] == root["owning_org_unit_id"]
    assert record["owning_org_unit_code"] == "test-root"

    aggregations = client.get(
        "/api/v1/aggregations", params={"owning_org_unit_id": root["owning_org_unit_id"]},
    )
    assert aggregations.status_code == 200, aggregations.text
    assert {item["id"] for item in aggregations.json()} == {root["id"], child["id"]}
    assert client.get(
        "/api/v1/aggregations", params={"owning_org_unit_id": 999999},
    ).json() == []

    records = client.get(
        "/api/v1/records", params={"owning_org_unit_id": root["owning_org_unit_id"]},
    )
    assert records.status_code == 200, records.text
    assert [item["id"] for item in records.json()] == [record["id"]]

    searched = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "field": "owning_org_unit_id",
                "operator": "eq",
                "value": root["owning_org_unit_id"],
            },
            "limit": 10,
        },
    )
    assert searched.status_code == 200, searched.text
    assert [item["id"] for item in searched.json()["items"]] == [record["id"]]
    assert searched.json()["items"][0]["owning_org_unit_name"] == "Test Root"


def test_browse_and_dashboard_present_organizational_owner(client: TestClient):
    root = client.post(
        "/api/v1/aggregations",
        json={
            "aggregation_number": "OWN-DASH",
            "title": "Dashboard holdings",
            "classification_id": 1,
        },
    ).json()
    record = client.post(
        "/api/v1/records",
        json={
            "aggregation_id": root["id"],
            "record_number": "OWN-DASH-REC",
            "title": "Dashboard record",
        },
    ).json()

    browsed = client.get("/api/v1/browse/classifications/1/aggregations")
    assert browsed.status_code == 200, browsed.text
    assert browsed.json()["items"][0]["owning_org_unit_name"] == "Test Root"
    filtered_out = client.get(
        "/api/v1/browse/classifications/1/aggregations",
        params={"owning_org_unit_id": 999999},
    )
    assert filtered_out.status_code == 200, filtered_out.text
    assert filtered_out.json()["items"] == []

    dashboard = client.get("/api/v1/dashboard/ownership-counts")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json() == [{
        "org_unit_id": root["owning_org_unit_id"],
        "org_unit_code": "test-root",
        "org_unit_name": "Test Root",
        "aggregation_count": 1,
        "record_count": 1,
    }]
    assert record["owning_org_unit_id"] == dashboard.json()[0]["org_unit_id"]

    first_update = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "Dashboard record, revised"},
        headers={"If-Match": str(record["version"])},
    )
    assert first_update.status_code == 200, first_update.text
    second_update = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "Dashboard record, revised again"},
        headers={"If-Match": str(first_update.json()["version"])},
    )
    assert second_update.status_code == 200, second_update.text

    recent_activity = client.get(
        "/api/v1/auth/me/recent-activity", params={"limit": 7},
    )
    assert recent_activity.status_code == 200, recent_activity.text
    assert [
        (item["entity_type"], item["entity_id"], item["operation"])
        for item in recent_activity.json()
        if item["entity_type"] == "record" and item["operation"] == "UPDATE"
    ] == [("record", record["id"], "UPDATE")]

    summary = client.get("/api/v1/dashboard/summary", params={"recent_limit": 7})
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["overview_counts"]["aggregations"] == 1
    assert payload["overview_counts"]["records"] == 1
    assert payload["ownership_counts"] == dashboard.json()
    assert payload["unclassified_root_count"] == 0
    assert payload["classification_metrics"]["terminal_count"] == 1
    assert {
        (item["entity_type"], item["entity_id"], item["operation"])
        for item in payload["recent_activity"]
    } >= {
        ("aggregation", root["id"], "CREATE"),
        ("record", record["id"], "CREATE"),
    }
    assert [
        (item["entity_type"], item["entity_id"], item["operation"])
        for item in payload["recent_activity"]
        if item["entity_type"] == "record" and item["operation"] == "UPDATE"
    ] == [("record", record["id"], "UPDATE")]
