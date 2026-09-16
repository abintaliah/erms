import os

import psycopg
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
        headers={"If-Match": str(child["version"])},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"
    child = response.json()

    response = client.patch(
        f"/api/v1/aggregations/{aggregation['id']}",
        json={"parent_aggregation_id": child["id"]},
        headers={"If-Match": str(aggregation["version"])},
    )
    assert response.status_code == 409

    assert client.delete(f"/api/v1/aggregations/{child['id']}", headers={"If-Match": str(child["version"])}).status_code == 204
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
        f"/api/v1/records/{record['id']}", json={"title": "Updated record"},
        headers={"If-Match": str(record["version"])},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated record"
    record = response.json()

    response = client.post(
        "/api/v1/records",
        json={"aggregation_id": 999999, "record_number": "REC-002", "title": "Orphan"},
    )
    assert response.status_code == 409

    assert client.delete(f"/api/v1/records/{record['id']}", headers={"If-Match": str(record["version"])}).status_code == 204


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
        headers={"If-Match": str(first["version"])},
    )
    assert response.status_code == 200
    assert response.json()["file_name"] == "renamed.pdf"
    first = response.json()

    assert client.delete(f"/api/v1/digital-components/{first['id']}", headers={"If-Match": str(first["version"])}).status_code == 204


def test_parent_deletion_is_rejected(client: TestClient, aggregation: dict, record: dict):
    response = client.delete(f"/api/v1/aggregations/{aggregation['id']}", headers={"If-Match": str(aggregation["version"])})
    assert response.status_code == 409


def test_record_deletion_cascades_to_components_and_content(client: TestClient, record: dict):
    component = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1},
        files={"file": ("delete-with-record.txt", b"content", "text/plain")},
    ).json()

    deleted = client.delete(
        f"/api/v1/records/{record['id']}",
        headers={"If-Match": str(record["version"])},
    )

    assert deleted.status_code == 204
    assert client.get(f"/api/v1/records/{record['id']}").status_code == 404
    assert client.get(f"/api/v1/digital-components/{component['id']}").status_code == 404
    assert client.get(f"/api/v1/digital-components/{component['id']}/content").status_code == 404


def test_closed_aggregation_makes_its_entire_subtree_immutable(client: TestClient):
    root = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CLOSE-ROOT", "title": "Closed root",
    }).json()
    child = client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": root["id"], "aggregation_number": "CLOSE-CHILD",
        "title": "Child",
    }).json()
    sibling = client.post("/api/v1/aggregations", json={
        "aggregation_number": "CLOSE-SIBLING", "title": "Independent root",
    }).json()
    record = client.post("/api/v1/records", json={
        "aggregation_id": child["id"], "record_number": "CLOSE-REC", "title": "Protected record",
    }).json()
    component = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1}, files={"file": ("locked.txt", b"locked", "text/plain")},
    ).json()

    future = client.patch(
        f"/api/v1/aggregations/{root['id']}", json={"date_closed": "2999-01-01T00:00:00Z"},
        headers={"If-Match": str(root["version"])},
    )
    assert future.status_code == 422

    closed = client.patch(
        f"/api/v1/aggregations/{root['id']}", json={"date_closed": root["date_created"]},
        headers={"If-Match": str(root["version"])},
    )
    assert closed.status_code == 200
    root = closed.json()

    assert client.patch(
        f"/api/v1/aggregations/{root['id']}", json={"title": "Cannot rename"},
        headers={"If-Match": str(root["version"])},
    ).status_code == 409
    assert client.patch(
        f"/api/v1/aggregations/{root['id']}", json={"date_closed": "2026-01-01T00:00:00Z"},
        headers={"If-Match": str(root["version"])},
    ).status_code == 409
    assert client.patch(
        f"/api/v1/aggregations/{child['id']}", json={"description": "Cannot edit inherited closure"},
        headers={"If-Match": str(child["version"])},
    ).status_code == 409

    assert client.get(f"/api/v1/records/{record['id']}").status_code == 200
    assert client.get(f"/api/v1/digital-components/{component['id']}/content").content == b"locked"
    assert client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "No"},
        headers={"If-Match": str(record["version"])},
    ).status_code == 409
    assert client.delete(
        f"/api/v1/digital-components/{component['id']}",
        headers={"If-Match": str(component["version"])},
    ).status_code == 409
    assert client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 2}, files={"file": ("no.txt", b"no", "text/plain")},
    ).status_code == 409
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with pytest.raises(psycopg.errors.RaiseException):
            connection.execute(
                "UPDATE digital_component_blobs SET content = %s WHERE digital_component_id = %s",
                (b"bypass", component["id"]),
            )
        connection.rollback()
    assert client.post("/api/v1/records", json={
        "aggregation_id": child["id"], "record_number": "CLOSE-NO", "title": "No",
    }).status_code == 409
    assert client.post("/api/v1/aggregations", json={
        "parent_aggregation_id": child["id"], "aggregation_number": "CLOSE-NO-CHILD", "title": "No",
    }).status_code == 409
    assert client.delete(
        f"/api/v1/aggregations/{child['id']}", headers={"If-Match": str(child["version"])},
    ).status_code == 409

    reopened = client.patch(
        f"/api/v1/aggregations/{root['id']}", json={"date_closed": None},
        headers={"If-Match": str(root["version"])},
    )
    assert reopened.status_code == 200
    updated_record = client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "Allowed again"},
        headers={"If-Match": str(record["version"])},
    )
    assert updated_record.status_code == 200

    child_closed = client.patch(
        f"/api/v1/aggregations/{child['id']}", json={"date_closed": child["date_created"]},
        headers={"If-Match": str(child["version"])},
    )
    assert child_closed.status_code == 200
    assert client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "Still blocked"},
        headers={"If-Match": str(updated_record.json()["version"])},
    ).status_code == 409
    sibling_record = client.post("/api/v1/records", json={
        "aggregation_id": sibling["id"], "record_number": "CLOSE-SIB-REC", "title": "Independent",
    })
    assert sibling_record.status_code == 201


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


def test_api_change_creates_correlated_history(client: TestClient):
    request_id = "11111111-1111-4111-8111-111111111111"
    correlation_id = "22222222-2222-4222-8222-222222222222"
    response = client.post(
        "/api/v1/aggregations",
        headers={
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
            "X-Change-Reason": "Created for audit testing",
        },
        json={"aggregation_number": "AUDIT-001", "title": "Audited item"},
    )
    assert response.status_code == 201
    aggregation = response.json()
    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["X-Correlation-ID"] == correlation_id

    history_response = client.get(
        f"/api/v1/aggregations/{aggregation['id']}/history"
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    event = history[0]
    assert event["entity_type"] == "aggregation"
    assert event["entity_id"] == aggregation["id"]
    assert event["operation"] == "CREATE"
    assert event["actor_user_id"] == 1
    assert event["actor_name"] == "Test Administrator"
    assert event["actor_email"] == "admin@test.invalid"
    assert event["actor_type"] == "user"
    assert event["source"] == "api"
    assert event["request_id"] == request_id
    assert event["correlation_id"] == correlation_id
    assert event["reason"] == "Created for audit testing"
    assert event["before_state"] is None
    assert event["after_state"]["title"] == "Audited item"
    assert "title" in event["changed_fields"]
    assert event["metadata"] == {}


def test_event_source_is_controlled(client: TestClient):
    rejected = client.post(
        "/api/v1/aggregations",
        headers={"X-Event-Source": "made-up-client"},
        json={"aggregation_number": "SOURCE-INVALID", "title": "Invalid source"},
    )
    assert rejected.status_code == 400

    created = client.post(
        "/api/v1/aggregations",
        headers={"X-Event-Source": "web_ui"},
        json={"aggregation_number": "SOURCE-WEB", "title": "Web source"},
    )
    assert created.status_code == 201
    history = client.get(
        f"/api/v1/aggregations/{created.json()['id']}/history"
    ).json()
    assert history[0]["source"] == "web_ui"


def test_update_and_delete_snapshots_remain_available(
    client: TestClient, record: dict
):
    update_response = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "Changed title", "description": "Changed description"},
        headers={"If-Match": str(record["version"])},
    )
    assert update_response.status_code == 200

    delete_response = client.delete(f"/api/v1/records/{record['id']}", headers={"If-Match": str(update_response.json()["version"])})
    assert delete_response.status_code == 204

    history_response = client.get(f"/api/v1/records/{record['id']}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    assert [event["operation"] for event in history] == ["DELETE", "UPDATE", "CREATE"]

    update_event = history[1]
    assert update_event["before_state"]["title"] == "Example record"
    assert update_event["after_state"]["title"] == "Changed title"
    assert update_event["changed_fields"] == ["description", "title"]

    delete_event = history[0]
    assert delete_event["before_state"]["title"] == "Changed title"
    assert delete_event["after_state"] is None


def test_event_history_is_read_only_and_searchable(
    client: TestClient, aggregation: dict
):
    history = client.get(
        "/api/v1/event-history",
        params={"entity_type": "aggregation", "entity_id": aggregation["id"]},
    )
    assert history.status_code == 200
    event = history.json()[0]

    get_response = client.get(f"/api/v1/event-history/{event['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == event["id"]

    search_response = client.post(
        "/api/v1/event-history/search",
        json={
            "where": {
                "and": [
                    {"field": "entity_type", "operator": "eq", "value": "aggregation"},
                    {"field": "operation", "operator": "eq", "value": "CREATE"},
                    {"field": "request_id", "operator": "is_not_null"},
                ]
            }
        },
    )
    assert search_response.status_code == 200
    assert search_response.json()["total"] == 1

    assert client.patch(
        f"/api/v1/event-history/{event['id']}", json={"reason": "tampered"}
    ).status_code == 405
    assert client.delete(f"/api/v1/event-history/{event['id']}").status_code == 405


def test_request_context_headers_are_validated(client: TestClient):
    response = client.get("/health", headers={"X-Correlation-ID": "not-a-uuid"})
    assert response.status_code == 400

    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == response.headers["X-Correlation-ID"]


def test_optimistic_concurrency_requires_current_version(
    client: TestClient, record: dict
):
    missing = client.patch(
        f"/api/v1/records/{record['id']}", json={"title": "No precondition"}
    )
    assert missing.status_code == 428

    updated = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "First writer"},
        headers={"If-Match": str(record["version"])},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == record["version"] + 1

    stale = client.patch(
        f"/api/v1/records/{record['id']}",
        json={"title": "Stale writer"},
        headers={"If-Match": str(record["version"])},
    )
    assert stale.status_code == 412
    assert stale.json()["detail"]["current_version"] == updated.json()["version"]


def test_upload_download_replace_and_delete_content(client: TestClient, record: dict):
    content = "مرحبا ERMS".encode()
    uploaded = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": "1"},
        files={"file": ("note.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 201
    component = uploaded.json()
    assert component["content_status"] == "available"
    assert component["storage_backend"] == "postgresql"
    assert component["size_in_bytes"] == len(content)
    assert component["checksum_algo"] == "sha256"

    downloaded = client.get(
        f"/api/v1/digital-components/{component['id']}/content"
    )
    assert downloaded.status_code == 200
    assert downloaded.content == content

    replacement = b"replacement"
    replaced = client.put(
        f"/api/v1/digital-components/{component['id']}/content",
        files={"file": ("replacement.bin", replacement, "application/octet-stream")},
        headers={"If-Match": str(component["version"])},
    )
    assert replaced.status_code == 200
    component = replaced.json()
    assert component["version"] == 2
    assert client.get(
        f"/api/v1/digital-components/{component['id']}/content"
    ).content == replacement

    deleted = client.delete(
        f"/api/v1/digital-components/{component['id']}/content",
        headers={"If-Match": str(component["version"])},
    )
    assert deleted.status_code == 200
    assert deleted.json()["content_status"] == "deleted"
    assert client.get(
        f"/api/v1/digital-components/{component['id']}/content"
    ).status_code == 404

    history = client.get(
        f"/api/v1/digital-components/{component['id']}/history"
    ).json()
    operations = [event["operation"] for event in history]
    assert "CONTENT_UPLOADED" in operations
    assert "CONTENT_DOWNLOADED" in operations
    assert "CONTENT_REPLACED" in operations
    assert "CONTENT_DELETED" in operations
    domain_events = [event for event in history if event["operation"].startswith("CONTENT_")]
    assert all(event["before_state"] is None for event in domain_events)
    assert all(event["after_state"] is None for event in domain_events)


def test_pdf_rendition_is_inline_and_audited(client: TestClient, record: dict):
    pdf = b"%PDF-1.4\n% minimal test fixture\n%%EOF"
    uploaded = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": "1"},
        files={"file": ("letter.pdf", pdf, "application/pdf")},
    ).json()
    response = client.get(f"/api/v1/digital-components/{uploaded['id']}/rendition")
    assert response.status_code == 200
    assert response.content == pdf
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline;")
    history = client.get(f"/api/v1/digital-components/{uploaded['id']}/history").json()
    assert "CONTENT_VIEWED" in [event["operation"] for event in history]


def test_unsupported_preview_preserves_original_download(client: TestClient, record: dict):
    uploaded = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": "1"},
        files={"file": ("archive.zip", b"not really a zip", "application/zip")},
    ).json()
    assert client.get(f"/api/v1/digital-components/{uploaded['id']}/rendition").status_code == 415
    assert client.get(f"/api/v1/digital-components/{uploaded['id']}/content").content == b"not really a zip"


def test_browser_native_image_preview_preserves_mime_type_and_is_audited(client: TestClient, record: dict):
    image = b"\x89PNG\r\n\x1a\nsynthetic-test-image"
    uploaded = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": "1"},
        files={"file": ("scan.png", image, "image/png")},
    ).json()
    response = client.get(f"/api/v1/digital-components/{uploaded['id']}/rendition")
    assert response.status_code == 200
    assert response.content == image
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["content-disposition"].startswith("inline;")
    history = client.get(f"/api/v1/digital-components/{uploaded['id']}/history").json()
    viewed = next(event for event in history if event["operation"] == "CONTENT_VIEWED")
    assert viewed["metadata"]["rendering_method"] == "browser-native"


def test_upload_size_limit(client: TestClient, record: dict, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_SIZE_BYTES", "4")
    response = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": "1"},
        files={"file": ("too-large.bin", b"12345", "application/octet-stream")},
    )
    assert response.status_code == 413
def test_record_draft_commits_metadata_and_ordered_content_atomically(client, aggregation):
    draft_response = client.post("/api/v1/record-drafts", json={})
    assert draft_response.status_code == 201
    draft = draft_response.json()

    assert client.get("/api/v1/records").json() == []
    first = client.post(
        f"/api/v1/record-drafts/{draft['id']}/components",
        data={"component_order": "1"}, files={"file": ("first.txt", b"first", "text/plain")},
    )
    second = client.post(
        f"/api/v1/record-drafts/{draft['id']}/components",
        data={"component_order": "2"}, files={"file": ("second.pdf", b"second", "application/pdf")},
    )
    assert first.status_code == second.status_code == 201

    reordered = client.put(
        f"/api/v1/record-drafts/{draft['id']}/components/order",
        json={"components": [
            {"id": first.json()["id"], "component_order": 2},
            {"id": second.json()["id"], "component_order": 1},
        ]},
    )
    assert reordered.status_code == 204
    staged = client.get(f"/api/v1/record-drafts/{draft['id']}/components").json()
    assert [item["file_name"] for item in staged] == ["second.pdf", "first.txt"]
    assert all(item["content_status"] == "staged" for item in staged)

    updated = client.patch(f"/api/v1/record-drafts/{draft['id']}", json={
        "aggregation_id": aggregation["id"], "record_number": "REC-DRAFT-1",
        "title": "Created as a package", "description": "Metadata and files commit together",
    })
    assert updated.status_code == 200
    committed = client.post(f"/api/v1/record-drafts/{draft['id']}/commit")
    assert committed.status_code == 201
    record = committed.json()
    components = client.get("/api/v1/digital-components", params={"record_id": record["id"]}).json()
    assert [item["file_name"] for item in components] == ["second.pdf", "first.txt"]
    assert client.get(f"/api/v1/digital-components/{components[0]['id']}/content").content == b"second"
    assert client.get(f"/api/v1/record-drafts/{draft['id']}").status_code == 404


def test_record_draft_component_can_be_removed_and_incomplete_commit_rolls_back(client):
    draft = client.post("/api/v1/record-drafts", json={}).json()
    component = client.post(
        f"/api/v1/record-drafts/{draft['id']}/components",
        data={"component_order": "1"}, files={"file": ("remove.txt", b"remove", "text/plain")},
    ).json()
    removed = client.delete(f"/api/v1/record-drafts/{draft['id']}/components/{component['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/record-drafts/{draft['id']}/components").json() == []
    failed = client.post(f"/api/v1/record-drafts/{draft['id']}/commit")
    assert failed.status_code == 422
    assert client.get("/api/v1/records").json() == []


def test_committed_components_can_be_reordered_and_removed_without_order_gaps(client, record):
    components = []
    for position, name in enumerate(("one.txt", "two.txt", "three.txt"), 1):
        response = client.post(
            f"/api/v1/records/{record['id']}/digital-components/upload",
            data={"component_order": str(position)}, files={"file": (name, name.encode(), "text/plain")},
        )
        assert response.status_code == 201
        components.append(response.json())
    response = client.put(
        f"/api/v1/records/{record['id']}/digital-components/order",
        json={"components": [
            {"id": components[2]["id"], "component_order": 1},
            {"id": components[0]["id"], "component_order": 2},
            {"id": components[1]["id"], "component_order": 3},
        ]},
    )
    assert response.status_code == 204
    reordered = client.get("/api/v1/digital-components", params={"record_id": record["id"]}).json()
    assert [item["file_name"] for item in reordered] == ["three.txt", "one.txt", "two.txt"]
    assert client.delete(
        f"/api/v1/digital-components/{reordered[1]['id']}",
        headers={"If-Match": str(reordered[1]["version"])},
    ).status_code == 204
    remaining = client.get("/api/v1/digital-components", params={"record_id": record["id"]}).json()
    assert [item["component_order"] for item in remaining] == [1, 2]
