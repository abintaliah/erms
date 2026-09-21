import os

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row


def test_information_governance_can_correct_root_owner_and_creator_role(client: TestClient):
    root = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CORRECT-ROOT", "title": "Incorrect owner",
        "classification_id": 1,
    }).json()
    child = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CORRECT-CHILD", "title": "Child",
        "parent_aggregation_id": root["id"],
    }).json()
    record = client.post("/api/v1/records", json={
        "record_number": "CORRECT-REC", "title": "Record",
        "aggregation_id": child["id"],
    }).json()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        unit_id = connection.execute(
            "INSERT INTO org_units(code,name) VALUES ('CORRECTED','Corrected Unit') RETURNING id"
        ).fetchone()["id"]
        role_id = connection.execute(
            "INSERT INTO roles(org_unit_id,code,name) VALUES (%s,'corrected-role','Corrected Role') RETURNING id",
            (unit_id,),
        ).fetchone()["id"]

    preview = client.get(
        f"/api/v1/aggregations/{root['id']}/ownership-correction-preview",
        params={"destination_role_id": role_id},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["affected_aggregation_count"] == 2
    assert preview.json()["affected_record_count"] == 1
    assert preview.json()["creator_role_id"] == 1
    assert preview.json()["creator_role_grant_count"] > 0

    corrected = client.post(
        f"/api/v1/aggregations/{root['id']}/correct-ownership",
        json={"destination_role_id": role_id, "reason": "Creator selected the wrong unit"},
    )
    assert corrected.status_code == 200, corrected.text
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        assert connection.execute(
            "SELECT count(*)::int AS count FROM aggregations WHERE id=ANY(%s) AND owning_org_unit_id=%s",
            ([root["id"], child["id"]], unit_id),
        ).fetchone()["count"] == 2
        assert connection.execute(
            "SELECT owning_org_unit_id FROM records WHERE id=%s", (record["id"],),
        ).fetchone()["owning_org_unit_id"] == unit_id
        assert connection.execute(
            "SELECT count(*)::int AS count FROM organizational_ownership_diagnostics"
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT count(*)::int AS count FROM aggregation_acl_grants WHERE aggregation_id=%s AND role_id=1",
            (root["id"],),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT count(*)::int AS count FROM aggregation_acl_grants WHERE aggregation_id=%s AND role_id=%s",
            (root["id"], role_id),
        ).fetchone()["count"] > 0
        event = connection.execute(
            "SELECT reason FROM event_history WHERE entity_type='aggregation' AND entity_id=%s AND operation='OWNERSHIP_CORRECTED'",
            (root["id"],),
        ).fetchone()
        assert event["reason"] == "Creator selected the wrong unit"


def test_ownership_correction_rejects_child_aggregation(client: TestClient):
    root = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CORRECT-PARENT", "title": "Parent", "classification_id": 1,
    }).json()
    child = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CORRECT-NOT-ROOT", "title": "Child",
        "parent_aggregation_id": root["id"],
    }).json()
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        unit_id = connection.execute(
            "INSERT INTO org_units(code,name) VALUES ('OTHER-CORRECT','Other') RETURNING id"
        ).fetchone()["id"]
        role_id = connection.execute(
            "INSERT INTO roles(org_unit_id,code,name) VALUES (%s,'other-correct','Other') RETURNING id",
            (unit_id,),
        ).fetchone()["id"]
    response = client.get(
        f"/api/v1/aggregations/{child['id']}/ownership-correction-preview",
        params={"destination_role_id": role_id},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "root_ownership_correction_only"
