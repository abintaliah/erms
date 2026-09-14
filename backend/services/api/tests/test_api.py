import os

import pytest
from fastapi.testclient import TestClient

from backend.services.api.config import load_environment


def test_real_environment_overrides_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PRECEDENCE_TEST=from-dotenv\n")
    monkeypatch.setenv("PRECEDENCE_TEST", "from-environment")

    load_environment(env_file)

    assert os.environ["PRECEDENCE_TEST"] == "from-environment"


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_aggregation_crud_and_hierarchy(client: TestClient, aggregation: dict):
    child_response = client.post(
        "/api/v1/aggregations",
        json={
            "parent_aggregation_id": aggregation["id"],
            "aggregation_number": "AGG-002",
            "title": "Child aggregation",
        },
    )
    assert child_response.status_code == 201
    child = child_response.json()
    assert child["date_opened"] == child["date_created"]

    response = client.get(
        "/api/v1/aggregations",
        params={"parent_aggregation_id": aggregation["id"]},
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [child["id"]]

    response = client.patch(
        f"/api/v1/aggregations/{child['id']}",
        json={"description": "Updated description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"

    response = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"parent_aggregation_id": child["id"]},
    )
    assert response.status_code == 409

    assert client.delete(f"/api/v1/aggregations/{child['id']}").status_code == 204
    assert client.get(f"/api/v1/aggregations/{child['id']}").status_code == 404


def test_aggregation_number_must_be_unique(client: TestClient, aggregation: dict):
    response = client.post(
        "/api/v1/aggregations",
        json={"aggregation_number": aggregation["aggregation_number"], "title": "Duplicate"},
    )
    assert response.status_code == 409


def test_record_crud_and_required_aggregation(
    client: TestClient, aggregation: dict, record: dict
):
    assert record["date_originated"] == record["date_created"]

    response = client.get(
        "/api/v1/records", params={"aggregation_id": aggregation["id"]}
    )
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [record["id"]]

    response = client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "Updated record"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated record"

    response = client.post(
        "/api/v1/records",
        json={"aggregation_id": 999999, "record_number": "REC-002", "title": "Orphan"},
    )
    assert response.status_code == 409

    assert client.delete(f"/api/v1/records/{record['id']}").status_code == 204


def test_digital_component_crud_and_order(client: TestClient, record: dict):
    component_payload = {
        "record_id": record["id"],
        "file_name": "page-1.pdf",
        "mime_type": "application/pdf",
        "size_in_bytes": 2048,
        "checksum_algo": "SHA-256",
        "checksum_value": "a" * 64,
    }
    second_response = client.post(
        "/api/v1/digital-components",
        json={**component_payload, "component_order": 2, "file_name": "page-2.pdf"},
    )
    first_response = client.post(
        "/api/v1/digital-components",
        json={**component_payload, "component_order": 1},
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201
    first = first_response.json()
    assert first["date_originated"] == first["date_created"]

    response = client.get(
        "/api/v1/digital-components", params={"record_id": record["id"]}
    )
    assert response.status_code == 200
    assert [item["component_order"] for item in response.json()] == [1, 2]

    duplicate_response = client.post(
        "/api/v1/digital-components",
        json={**component_payload, "component_order": 1, "file_name": "duplicate.pdf"},
    )
    assert duplicate_response.status_code == 409

    response = client.patch(
        f"/api/v1/digital-components/{first['id']}",
        json={"file_name": "renamed.pdf"},
    )
    assert response.status_code == 200
    assert response.json()["file_name"] == "renamed.pdf"

    assert client.delete(f"/api/v1/digital-components/{first['id']}").status_code == 204


def test_parent_deletion_is_rejected(client: TestClient, aggregation: dict, record: dict):
    response = client.delete(f"/api/v1/aggregations/{aggregation['id']}")
    assert response.status_code == 409


def test_request_validation(client: TestClient, record: dict):
    response = client.post(
        "/api/v1/digital-components",
        json={
            "record_id": record["id"],
            "component_order": 0,
            "file_name": "bad.txt",
            "mime_type": "text/plain",
            "size_in_bytes": -1,
            "checksum_algo": "SHA-256",
            "checksum_value": "abc",
        },
    )
    assert response.status_code == 422


def create_search_records(client: TestClient, aggregation: dict) -> list[dict]:
    records = []
    for record_number, title, description, originated in (
        ("REC-S-001", "Alpha Contract", None, "2025-02-01T00:00:00Z"),
        ("REC-S-002", "Draft contract", "Pending review", "2025-06-01T00:00:00Z"),
        ("REC-S-003", "Beta Note", "Final note", "2026-01-01T00:00:00Z"),
    ):
        response = client.post(
            "/api/v1/records",
            json={
                "aggregation_id": aggregation["id"],
                "record_number": record_number,
                "title": title,
                "description": description,
                "date_originated": originated,
            },
        )
        assert response.status_code == 201
        records.append(response.json())
    return records


def test_nested_boolean_search(client: TestClient, aggregation: dict):
    create_search_records(client, aggregation)
    response = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "and": [
                    {
                        "field": "aggregation_id",
                        "operator": "in",
                        "value": [aggregation["id"]],
                    },
                    {
                        "field": "date_originated",
                        "operator": "between",
                        "value": [
                            "2025-01-01T00:00:00Z",
                            "2025-12-31T23:59:59Z",
                        ],
                    },
                    {
                        "or": [
                            {
                                "field": "title",
                                "operator": "contains_ci",
                                "value": "alpha",
                            },
                            {"field": "description", "operator": "is_null"},
                        ]
                    },
                    {
                        "not": {
                            "field": "title",
                            "operator": "contains_ci",
                            "value": "draft",
                        }
                    },
                ]
            },
            "sort": [{"field": "record_number", "direction": "desc"}],
            "limit": 10,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result["limit"] == 10
    assert result["offset"] == 0
    assert [item["record_number"] for item in result["items"]] == ["REC-S-001"]


@pytest.mark.parametrize(
    ("expression", "expected_total"),
    [
        ({"field": "record_number", "operator": "eq", "value": "REC-S-001"}, 1),
        ({"field": "record_number", "operator": "ne", "value": "REC-S-001"}, 2),
        ({"field": "id", "operator": "gt", "value": 1}, 2),
        ({"field": "id", "operator": "gte", "value": 1}, 3),
        ({"field": "id", "operator": "lt", "value": 2}, 1),
        ({"field": "id", "operator": "lte", "value": 2}, 2),
        (
            {
                "field": "record_number",
                "operator": "not_in",
                "value": ["REC-S-001", "REC-S-002"],
            },
            1,
        ),
        ({"field": "description", "operator": "is_not_null"}, 2),
        ({"field": "title", "operator": "starts_with_ci", "value": "alpha"}, 1),
        ({"field": "title", "operator": "ends_with_ci", "value": "NOTE"}, 1),
    ],
)
def test_search_comparison_operators(
    client: TestClient,
    aggregation: dict,
    expression: dict,
    expected_total: int,
):
    create_search_records(client, aggregation)
    response = client.post("/api/v1/records/search", json={"where": expression})
    assert response.status_code == 200
    assert response.json()["total"] == expected_total


def test_search_pagination_and_literal_wildcards(
    client: TestClient, aggregation: dict
):
    create_search_records(client, aggregation)
    wildcard_record = client.post(
        "/api/v1/records",
        json={
            "aggregation_id": aggregation["id"],
            "record_number": "REC-S-004",
            "title": "Literal 100%_match",
        },
    )
    assert wildcard_record.status_code == 201

    response = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "field": "title",
                "operator": "contains_ci",
                "value": "100%_match",
            },
            "sort": [{"field": "title", "direction": "asc"}],
            "limit": 1,
            "offset": 0,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result["items"][0]["record_number"] == "REC-S-004"


def test_all_entity_search_endpoints(
    client: TestClient, aggregation: dict, record: dict
):
    aggregation_response = client.post(
        "/api/v1/aggregations/search",
        json={
            "where": {
                "field": "aggregation_number",
                "operator": "eq",
                "value": aggregation["aggregation_number"],
            }
        },
    )
    assert aggregation_response.status_code == 200
    assert aggregation_response.json()["total"] == 1

    component_response = client.post(
        "/api/v1/digital-components",
        json={
            "record_id": record["id"],
            "component_order": 1,
            "file_name": "searchable.pdf",
            "mime_type": "application/pdf",
            "size_in_bytes": 1024,
            "checksum_algo": "SHA-256",
            "checksum_value": "a" * 64,
        },
    )
    assert component_response.status_code == 201
    response = client.post(
        "/api/v1/digital-components/search",
        json={
            "where": {
                "field": "size_in_bytes",
                "operator": "between",
                "value": [1000, 2000],
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_search_rejects_unsafe_or_invalid_grammar(
    client: TestClient, aggregation: dict
):
    create_search_records(client, aggregation)

    unknown_field = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "field": "title; DROP TABLE records; --",
                "operator": "eq",
                "value": "anything",
            }
        },
    )
    assert unknown_field.status_code == 422

    wrong_operator_type = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "field": "id",
                "operator": "contains_ci",
                "value": "1",
            }
        },
    )
    assert wrong_operator_type.status_code == 422

    mixed_expression = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "not": {"field": "id", "operator": "eq", "value": 1},
                "value": "not allowed on a logical expression",
            }
        },
    )
    assert mixed_expression.status_code == 422

    oversized_in = client.post(
        "/api/v1/records/search",
        json={
            "where": {
                "field": "id",
                "operator": "in",
                "value": list(range(101)),
            }
        },
    )
    assert oversized_in.status_code == 422

    expression = {"field": "id", "operator": "eq", "value": 1}
    for _ in range(6):
        expression = {"not": expression}
    excessive_depth = client.post(
        "/api/v1/records/search", json={"where": expression}
    )
    assert excessive_depth.status_code == 422
