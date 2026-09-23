import os

import psycopg
from fastapi.testclient import TestClient


def levels(client: TestClient) -> dict[str, dict]:
    response = client.get("/api/v1/security-levels")
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()}


def test_seeded_catalogue_and_lowest_level_defaults(client: TestClient, aggregation: dict, record: dict):
    catalogue = levels(client)
    assert [(item["code"], item["level_number"]) for item in catalogue.values()] == [
        ("G", 0), ("R", 50), ("S", 75), ("TS", 100),
    ]
    assert aggregation["security_level_id"] == catalogue["G"]["id"]
    assert record["security_level_id"] == catalogue["G"]["id"]
    role = client.get("/api/v1/roles/1")
    assert role.status_code == 200
    assert role.json()["security_level_id"] == catalogue["G"]["id"]
    assert catalogue["G"]["roles_assigned_count"] >= 1
    assert catalogue["G"]["aggregation_count"] >= 1
    assert catalogue["G"]["record_count"] >= 1
    for level in catalogue.values():
        history = client.get(f"/api/v1/security-levels/{level['id']}/history")
        assert history.status_code == 200, history.text
        assert sum(event["operation"] == "CREATE" for event in history.json()) == 1


def test_security_level_history_uses_standard_event_history(client: TestClient):
    created = client.post("/api/v1/security-levels", json={
        "code": "HIST",
        "name": "History test level",
        "level_number": 60,
        "prevents_disposition": False,
    })
    assert created.status_code == 201, created.text

    history = client.get(f"/api/v1/security-levels/{created.json()['id']}/history")
    assert history.status_code == 200, history.text
    assert any(
        event["entity_type"] == "security_level"
        and event["entity_id"] == created.json()["id"]
        for event in history.json()
    )


def test_child_aggregation_defaults_to_parent_but_record_defaults_to_baseline(
    client: TestClient, aggregation: dict
):
    catalogue = levels(client)
    # This test intentionally creates Secret information, so its test actor must
    # first hold a clearance at least as high as the requested resource level.
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "UPDATE roles SET security_level_id=%s WHERE id=1", (catalogue["TS"]["id"],),
        )
    upgraded = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"security_level_id": catalogue["S"]["id"]},
        headers={"If-Match": str(aggregation["version"]), "X-Change-Reason": "Classification changed"},
    )
    assert upgraded.status_code == 200, upgraded.text
    child = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": aggregation["id"],
        "aggregation_number": "AGG-CHILD",
        "title": "Inherited parent level",
    })
    assert child.status_code == 201, child.text
    assert child.json()["security_level_id"] == catalogue["S"]["id"]
    created_record = client.post("/api/v1/records", json={
        "aggregation_id": aggregation["id"], "record_number": "REC-G", "title": "Baseline",
    })
    assert created_record.status_code == 201, created_record.text
    assert created_record.json()["security_level_id"] == catalogue["G"]["id"]


def test_parent_must_not_be_lower_than_child_and_lowering_requires_reason(
    client: TestClient, aggregation: dict, record: dict
):
    catalogue = levels(client)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE roles SET security_level_id=%s WHERE id=1", (catalogue["TS"]["id"],))
    invalid = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"security_level_id": catalogue["R"]["id"]},
        headers={"If-Match": str(record["version"]), "X-Change-Reason": "Classification changed"},
    )
    assert invalid.status_code == 409
    parent = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"security_level_id": catalogue["R"]["id"]},
        headers={"If-Match": str(aggregation["version"]), "X-Change-Reason": "Classification changed"},
    )
    assert parent.status_code == 200, parent.text
    record = client.get(f"/api/v1/records/{record['id']}").json()
    raised = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"security_level_id": catalogue["R"]["id"]},
        headers={"If-Match": str(record["version"]), "X-Change-Reason": "Classification changed"},
    )
    assert raised.status_code == 200, raised.text
    no_reason = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"security_level_id": catalogue["G"]["id"]},
        headers={"If-Match": str(raised.json()["version"])},
    )
    assert no_reason.status_code == 422
    lowered = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"security_level_id": catalogue["G"]["id"]},
        headers={"If-Match": str(raised.json()["version"]), "X-Change-Reason": "Reclassified"},
    )
    assert lowered.status_code == 200, lowered.text
    history = client.get(f"/api/v1/records/{record['id']}/history").json()
    assert "SECURITY_LEVEL_UPGRADED" in {event["operation"] for event in history}
    assert "SECURITY_LEVEL_DOWNGRADED" in {event["operation"] for event in history}


def test_preview_and_apply_can_raise_ancestors_atomically(client: TestClient, aggregation: dict):
    catalogue = levels(client)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute("UPDATE roles SET security_level_id=%s WHERE id=1", (catalogue["TS"]["id"],))
    child = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": aggregation["id"],
        "aggregation_number": "AGG-CHILD", "title": "Child",
    }).json()
    preview_payload = {
        "resource_type": "aggregation", "resource_id": child["id"],
        "target_security_level_id": catalogue["TS"]["id"],
        "remedy": "raise_ancestors",
    }
    preview = client.post("/api/v1/security-level-changes/preview", json=preview_payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["conflict"] is True
    assert [row["id"] for row in preview.json()["affected_aggregations"]] == [aggregation["id"]]
    applied = client.post(
        "/api/v1/security-level-changes/apply",
        json={**preview_payload, "preview_token": preview.json()["preview_token"]},
        headers={"X-Change-Reason": "Required classification"},
    )
    assert applied.status_code == 200, applied.text
    assert client.get(f"/api/v1/aggregations/{aggregation['id']}").json()["security_level_id"] == catalogue["TS"]["id"]
    assert client.get(f"/api/v1/aggregations/{child['id']}").json()["security_level_id"] == catalogue["TS"]["id"]


def test_referenced_and_baseline_levels_cannot_be_deleted(client: TestClient):
    catalogue = levels(client)
    baseline = client.delete(
        f"/api/v1/security-levels/{catalogue['G']['id']}",
        headers={"If-Match": str(catalogue["G"]["version"])},
    )
    assert baseline.status_code == 409
    referenced = client.delete(
        f"/api/v1/security-levels/{catalogue['R']['id']}",
        headers={"If-Match": str(catalogue["R"]["version"])},
    )
    assert referenced.status_code == 204
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        role_id = connection.execute("SELECT id FROM roles LIMIT 1").fetchone()[0]
        connection.execute(
            "UPDATE roles SET security_level_id=%s WHERE id=%s",
            (catalogue["S"]["id"], role_id),
        )
    refreshed = client.get(f"/api/v1/security-levels/{catalogue['S']['id']}").json()
    denied = client.delete(
        f"/api/v1/security-levels/{refreshed['id']}",
        headers={"If-Match": str(refreshed["version"])},
    )
    assert denied.status_code == 409
