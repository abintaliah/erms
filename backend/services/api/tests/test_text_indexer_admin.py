from datetime import datetime, timedelta, timezone
import os

import psycopg
from psycopg.rows import dict_row
from fastapi.testclient import TestClient


def _payload(suffix: str = "one") -> dict:
    return {
        "name": f"Production indexer {suffix}",
        "external_id": f"production-indexer-{suffix}",
        "credential_name": f"Initial key {suffix}",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    }


def test_dedicated_privilege_is_seeded_only_to_approved_builtin_profiles(client: TestClient):
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        profiles = {
            row["code"] for row in connection.execute(
                """SELECT profile.code
                     FROM profiles profile
                     JOIN profile_privileges membership ON membership.profile_id=profile.id
                     JOIN privileges privilege ON privilege.id=membership.privilege_id
                    WHERE privilege.code='identity.text_indexers.administer'
                      AND profile.is_system"""
            ).fetchall()
        }
        service_privileges = {
            row["code"] for row in connection.execute(
                """SELECT privilege.code
                     FROM profiles profile
                     JOIN profile_privileges membership ON membership.profile_id=profile.id
                     JOIN privileges privilege ON privilege.id=membership.privilege_id
                    WHERE profile.code='TEXT_INDEXER_SERVICE'"""
            ).fetchall()
        }
    assert profiles == {"ALL_PRIVS", "SYS_ADMIN"}
    assert service_privileges == {"content.index.execute"}


def test_create_is_atomic_assigns_only_protected_role_and_reveals_key_once(client: TestClient):
    response = client.post("/api/v1/text-indexers", json=_payload())
    assert response.status_code == 201, response.text
    created = response.json()
    account = created["text_indexer"]
    credential = created["credential"]
    assert account["account_type"] == "service"
    assert account["status"] == "active"
    assert account["credential_count"] == 1
    assert account["active_credential_count"] == 1
    assert credential["api_key"].startswith(f"wti_{credential['credential_identifier']}.")

    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        assignments = connection.execute(
            """SELECT role.code,role.is_system,profile.code AS profile_code
                 FROM user_role_assignments assignment
                 JOIN roles role ON role.id=assignment.role_id
                 JOIN profiles profile ON profile.id=role.profile_id
                WHERE assignment.user_id=%s""",
            (account["id"],),
        ).fetchall()
        stored = connection.execute(
            "SELECT secret_hash FROM service_account_credentials WHERE service_user_id=%s",
            (account["id"],),
        ).fetchone()
    assert [dict(row) for row in assignments] == [{
        "code": "text-indexer-service", "is_system": True,
        "profile_code": "TEXT_INDEXER_SERVICE",
    }]
    assert credential["api_key"] not in stored["secret_hash"]

    detail = client.get(f"/api/v1/text-indexers/{account['id']}")
    assert detail.status_code == 200
    assert "api_key" not in detail.text
    assert "credentials" not in detail.json()
    page = client.get(
        f"/api/v1/text-indexers/{account['id']}/credentials",
        params={"history": "all", "limit": 5, "offset": 0},
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["retention_days"] == 365
    assert page.json()["items"][0]["credential_identifier"] == credential["credential_identifier"]


def test_credential_history_is_server_paginated_and_filterable(client: TestClient):
    account = client.post("/api/v1/text-indexers", json=_payload()).json()["text_indexer"]
    for number in range(6):
        response = client.post(
            f"/api/v1/text-indexers/{account['id']}/credentials",
            json={
                "name": f"Key {number}",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text
    first = client.get(
        f"/api/v1/text-indexers/{account['id']}/credentials",
        params={"limit": 5, "offset": 0},
    ).json()
    second = client.get(
        f"/api/v1/text-indexers/{account['id']}/credentials",
        params={"limit": 5, "offset": 5},
    ).json()
    assert first["total"] == second["total"] == 7
    assert len(first["items"]) == 5
    assert len(second["items"]) == 2
    revoked = first["items"][0]
    assert client.post(
        f"/api/v1/text-indexers/{account['id']}/credentials/{revoked['id']}/revoke"
    ).status_code == 204
    history = client.get(
        f"/api/v1/text-indexers/{account['id']}/credentials",
        params={"history": "history", "limit": 5},
    ).json()
    usable = client.get(
        f"/api/v1/text-indexers/{account['id']}/credentials",
        params={"history": "usable", "limit": 5},
    ).json()
    assert history["total"] == 1
    assert history["items"][0]["status"] == "revoked"
    assert usable["total"] == 6


def test_builtin_text_indexer_role_is_visible_on_request_and_read_only(client: TestClient):
    ordinary = client.get("/api/v1/roles")
    assert ordinary.status_code == 200
    assert "text-indexer-service" not in {role["code"] for role in ordinary.json()}

    visible = client.get("/api/v1/roles", params={"include_system": True})
    assert visible.status_code == 200
    builtin = next(role for role in visible.json() if role["code"] == "text-indexer-service")
    assert builtin["is_system"] is True
    summary = client.get(
        f"/api/v1/browse/organization/roles/{builtin['id']}/summary"
    )
    assert summary.status_code == 200
    assert summary.json()["is_system"] is True
    headers = {"If-Match": str(builtin["version"])}
    assert client.patch(
        f"/api/v1/roles/{builtin['id']}", headers=headers,
        json={"name": "Attempted mutation"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/roles/{builtin['id']}/deactivate", headers=headers,
    ).status_code == 409
    assert client.get(
        f"/api/v1/roles/{builtin['id']}/deletion-preflight"
    ).status_code == 409
    assert client.delete(
        f"/api/v1/roles/{builtin['id']}", headers=headers,
    ).status_code == 409


def test_multiple_identities_and_duplicate_external_id_rollback(client: TestClient):
    first = client.post("/api/v1/text-indexers", json=_payload("blue"))
    second = client.post("/api/v1/text-indexers", json=_payload("green"))
    assert first.status_code == second.status_code == 201
    duplicate = client.post("/api/v1/text-indexers", json={**_payload("duplicate"), "external_id": "production-indexer-blue"})
    assert duplicate.status_code == 409
    listed = client.get("/api/v1/text-indexers")
    assert {item["external_id"] for item in listed.json()} == {
        "production-indexer-blue", "production-indexer-green",
    }
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        assert connection.execute(
            "SELECT count(*) AS value FROM users WHERE name='Production indexer duplicate'"
        ).fetchone()["value"] == 0


def test_generic_workflows_cannot_mutate_text_indexer_or_assignment(client: TestClient):
    account = client.post("/api/v1/text-indexers", json=_payload()).json()["text_indexer"]
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        assignment = connection.execute(
            "SELECT id,version FROM user_role_assignments WHERE user_id=%s", (account["id"],)
        ).fetchone()
    assert client.patch(
        f"/api/v1/users/{account['id']}",
        headers={"If-Match": str(account["version"])}, json={"name": "Bypass"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/users/{account['id']}/suspend",
        headers={"If-Match": str(account["version"])},
    ).status_code == 409
    assert client.delete(
        f"/api/v1/user-role-assignments/{assignment['id']}",
        headers={"If-Match": str(assignment["version"])},
    ).status_code == 409

    suspended = client.post(
        f"/api/v1/text-indexers/{account['id']}/suspend",
        headers={"If-Match": str(account["version"])},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    activated = client.post(
        f"/api/v1/text-indexers/{account['id']}/unsuspend",
        headers={"If-Match": str(suspended.json()["version"])},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"


def test_dedicated_routes_reject_user_without_dedicated_privilege(client: TestClient):
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        profile_id = connection.execute(
            "INSERT INTO profiles(code,name) VALUES ('USERS_ONLY','Users only') RETURNING id"
        ).fetchone()[0]
        privilege_id = connection.execute(
            "SELECT id FROM privileges WHERE code='identity.users.administer'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO profile_privileges(profile_id,privilege_id) VALUES (%s,%s)",
            (profile_id, privilege_id),
        )
        connection.execute(
            "UPDATE roles SET profile_id=%s WHERE code='system-administrator'", (profile_id,)
        )
    assert client.get("/api/v1/text-indexers").status_code == 403
    assert client.get("/api/v1/text-indexers/health").status_code == 403
    assert client.post(
        "/api/v1/text-indexers/backfill", json={"batch_size": 1},
    ).status_code == 403
    assert client.post("/api/v1/text-indexers", json=_payload()).status_code == 403


def test_health_is_privacy_safe_and_backfill_is_bounded_and_idempotent(
    client: TestClient, record: dict,
):
    uploaded = client.post(
        f"/api/v1/records/{record['id']}/digital-components/upload",
        data={"component_order": 1},
        files={"file": ("legacy.txt", b"legacy searchable evidence", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    component_id = uploaded.json()["id"]
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        connection.execute(
            "DELETE FROM content_indexing_jobs WHERE digital_component_id=%s",
            (component_id,),
        )
        connection.execute(
            "DELETE FROM digital_component_search_documents WHERE digital_component_id=%s",
            (component_id,),
        )

    health = client.get("/api/v1/text-indexers/health")
    assert health.status_code == 200, health.text
    snapshot = health.json()
    assert snapshot["status"] == "attention_required"
    assert snapshot["drifted_documents"] == 1
    assert set(snapshot) == {
        "status", "observed_at", "ready_for_search", "drifted_documents",
        "blocking_jobs", "failed_jobs", "stale_documents", "active_workers",
        "metrics",
    }
    assert "secret" not in health.text.lower()
    assert "extracted_text" not in health.text

    assert client.post(
        "/api/v1/text-indexers/backfill", json={"batch_size": 0},
    ).status_code == 422
    assert client.post(
        "/api/v1/text-indexers/backfill", json={"batch_size": 501},
    ).status_code == 422
    first = client.post(
        "/api/v1/text-indexers/backfill", json={"batch_size": 1},
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"batch_size": 1, "drifted": 1, "queued": 1}
    second = client.post(
        "/api/v1/text-indexers/backfill", json={"batch_size": 1},
    )
    assert second.status_code == 200, second.text
    assert second.json() == {"batch_size": 1, "drifted": 0, "queued": 0}
