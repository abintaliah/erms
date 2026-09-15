import os

import psycopg
from fastapi.testclient import TestClient


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


def test_system_administrator_can_list_and_revoke_sessions(client: TestClient):
    sessions = client.get("/api/v1/auth/sessions")
    assert sessions.status_code == 200
    current = next(row for row in sessions.json() if row["is_current"])
    assert current["status"] == "active"
    response = client.delete(f"/api/v1/auth/sessions/{current['id']}")
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
