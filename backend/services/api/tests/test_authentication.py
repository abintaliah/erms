import os

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from backend.services.api.manage_auth import (
    BOOTSTRAP_ORG_UNIT_CODE,
    BOOTSTRAP_USER_EMAIL,
    bootstrap_administrator,
)


def test_authenticated_principal_includes_roles(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    principal = response.json()
    assert principal["user"]["email"] == "admin@test.invalid"
    assert principal["user"]["account_type"] == "human"
    assert [role["code"] for role in principal["roles"]] == ["system-administrator"]


def test_protected_api_rejects_missing_session(client: TestClient):
    cookies = dict(client.cookies)
    client.cookies.clear()
    assert client.get("/api/v1/users").status_code == 401
    for name, value in cookies.items():
        client.cookies.set(name, value)


def test_failed_login_is_persisted_despite_unauthorized_response(client: TestClient):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.invalid", "password": "Definitely-Wrong-Password!"},
    )
    assert response.status_code == 401
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        credential = connection.execute(
            "SELECT failed_attempt_count, last_failed_at FROM user_credentials WHERE user_id=1"
        ).fetchone()
        failed_events = connection.execute(
            "SELECT count(*) FROM event_history WHERE operation='AUTHENTICATION_FAILED'"
        ).fetchone()[0]
    assert credential == (1, credential[1])
    assert credential[1] is not None
    assert failed_events == 1


def test_logout_revokes_session_and_removes_browser_cookies(client: TestClient):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "erms_session=" in response.headers["set-cookie"]
    assert client.cookies.get("erms_session") is None
    assert client.cookies.get("erms_csrf") is None
    assert client.get("/api/v1/auth/me").status_code == 401


def test_temporary_password_requires_change_and_never_enters_audit_snapshot(client: TestClient):
    created = client.post(
        "/api/v1/users", json={"name": "New Human", "email": "new.human@test.invalid", "account_type": "human"}
    )
    assert created.status_code == 201
    issued = client.post(f"/api/v1/auth/users/{created.json()['id']}/temporary-password")
    assert issued.status_code == 200
    temporary_password = issued.json()["temporary_password"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "new.human@test.invalid", "password": temporary_password},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    client.headers["X-CSRF-Token"] = client.cookies.get("erms_csrf")
    assert client.get("/api/v1/records").status_code == 403
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": temporary_password, "new_password": "A-New-Secure-Password-456!"},
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me").json()["must_change_password"] is False

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        serialized = connection.execute("SELECT COALESCE(string_agg(row_to_json(e)::text, ''), '') FROM event_history e").fetchone()[0]
    assert temporary_password not in serialized
    assert "$argon2" not in serialized


def test_service_account_is_non_interactive_and_cannot_receive_password(client: TestClient):
    created = client.post(
        "/api/v1/users",
        json={
            "name": "Document Conversion Service",
            "email": "converter@test.invalid",
            "account_type": "service",
        },
    )
    assert created.status_code == 201
    assert created.json()["account_type"] == "service"
    issued = client.post(
        f"/api/v1/auth/users/{created.json()['id']}/temporary-password"
    )
    assert issued.status_code == 422
    assert issued.json()["detail"] == "local passwords require a human user with an email address"


def test_system_administrator_can_list_and_revoke_sessions(client: TestClient):
    sessions = client.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    current = next(row for row in sessions.json() if row["is_current"])
    assert current["status"] == "active"
    response = client.delete(f"/api/v1/auth/sessions/{current['id']}")
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_deactivating_user_revokes_sessions_and_prevents_authentication(client: TestClient):
    current = client.get("/api/v1/users/1").json()
    response = client.post(
        "/api/v1/users/1/deactivate",
        headers={"If-Match": str(current["version"])},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "inactive"
    assert client.get("/api/v1/auth/me").status_code == 401
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        assert connection.execute(
            "SELECT bool_and(revoked_at IS NOT NULL) FROM login_sessions WHERE user_id=1"
        ).fetchone()[0] is True


def test_empty_database_can_bootstrap_one_interactive_administrator(client: TestClient):
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    with psycopg.connect(
        os.environ["DATABASE_URL"], row_factory=psycopg.rows.dict_row
    ) as connection:
        connection.execute(
            """
            TRUNCATE login_sessions, user_credentials, user_role_assignments,
                     roles, users, org_units
            RESTART IDENTITY CASCADE
            """
        )
        result = bootstrap_administrator(connection)
        stored = connection.execute(
            """
            SELECT u.name, u.email, u.account_type, u.external_id,
                   c.password_hash, c.must_change_password, c.temporary_expires_at,
                   r.code AS role_code, ou.code AS org_unit_code
            FROM users AS u
            JOIN user_credentials AS c ON c.user_id = u.id
            JOIN user_role_assignments AS a ON a.user_id = u.id
            JOIN roles AS r ON r.id = a.role_id
            JOIN org_units AS ou ON ou.id = r.org_unit_id
            WHERE u.id = %s
            """,
            (result.user_id,),
        ).fetchone()
        events = connection.execute(
            """
            SELECT source, actor_type, reason, metadata
            FROM event_history
            WHERE metadata ->> 'provisioning_operation' = 'bootstrap_administrator'
            """
        ).fetchall()

    assert stored["name"] == "Bootstrap Administrator"
    assert stored["email"] == BOOTSTRAP_USER_EMAIL
    assert stored["account_type"] == "human"
    assert stored["external_id"] == "SYSTEM-BOOTSTRAP"
    assert stored["must_change_password"] is True
    assert stored["temporary_expires_at"] == result.expires_at
    assert stored["role_code"] == "system-administrator"
    assert stored["org_unit_code"] == BOOTSTRAP_ORG_UNIT_CODE
    assert PasswordHasher().verify(stored["password_hash"], result.temporary_password)
    assert len(events) == 4
    assert all(event["source"] == "administrative_tool" for event in events)
    assert all(event["actor_type"] == "automated_process" for event in events)
    assert all(event["reason"] == "Initial system bootstrap" for event in events)
    assert result.temporary_password not in str(events)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": BOOTSTRAP_USER_EMAIL, "password": result.temporary_password},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert [role["code"] for role in login.json()["roles"]] == ["system-administrator"]

    with psycopg.connect(
        os.environ["DATABASE_URL"], row_factory=psycopg.rows.dict_row
    ) as connection:
        with pytest.raises(RuntimeError, match="active system administrator already exists"):
            bootstrap_administrator(connection)


def test_bootstrap_refuses_nonempty_database_without_an_administrator(client: TestClient):
    with psycopg.connect(
        os.environ["DATABASE_URL"], row_factory=psycopg.rows.dict_row
    ) as connection:
        connection.execute(
            """
            TRUNCATE login_sessions, user_credentials, user_role_assignments,
                     roles, users, org_units
            RESTART IDENTITY CASCADE
            """
        )
        connection.execute(
            "INSERT INTO users (name, email) VALUES ('Existing User', 'existing@test.invalid')"
        )
        with pytest.raises(RuntimeError, match="users table is empty"):
            bootstrap_administrator(connection)
