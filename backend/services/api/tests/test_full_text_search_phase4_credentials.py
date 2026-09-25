from datetime import datetime, timedelta, timezone


def _service_user(client):
    created = client.post("/api/v1/text-indexers", json={
        "name": "Phase 4 Indexer", "external_id": "phase4-indexer",
        "credential_name": "Initial key",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    })
    assert created.status_code == 201, created.text
    return created.json()["text_indexer"]


def test_service_credential_lifecycle_and_one_time_secret(client):
    account = _service_user(client)
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    created = client.post(f"/api/v1/text-indexers/{account['id']}/credentials", json={
        "name": "Production indexer", "expires_at": expires,
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["api_key"].startswith(f"wti_{body['credential_identifier']}.")
    listed = client.get(f"/api/v1/text-indexers/{account['id']}")
    assert listed.status_code == 200
    assert "api_key" not in listed.text
    rotated = client.post(
        f"/api/v1/text-indexers/{account['id']}/credentials/{body['id']}/rotate",
        json={"name": "Replacement indexer", "expires_at": expires},
    )
    assert rotated.status_code == 201, rotated.text
    rows = client.get(f"/api/v1/text-indexers/{account['id']}").json()["credentials"]
    assert {row["status"] for row in rows} == {"active", "revoked"}
    revoked = client.post(
        f"/api/v1/text-indexers/{account['id']}/credentials/{rotated.json()['id']}/revoke"
    )
    assert revoked.status_code == 204


def test_person_account_cannot_receive_service_credential(client):
    person = client.get("/api/v1/auth/me").json()["user"]
    response = client.post(f"/api/v1/users/{person['id']}/api-credentials", json={
        "name": "Invalid", "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })
    assert response.status_code == 422
