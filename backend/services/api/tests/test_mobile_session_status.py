"""Passive mobile monitoring must detect expiry without becoming activity."""
import pytest

from .test_application_settings_phase5_authentication import make_session, session
from .test_application_settings import db, save
from .test_global_privilege_enforcement import _bearer
from .test_messaging import account

PATH = "/api/v1/auth/me/session-status"


def test_passive_status_requires_no_administrative_privilege(client):
    token, user, _ = account(client, privileges=())
    response = client.get(PATH, headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == user


def test_passive_checks_preserve_activity_and_deadlines_but_normal_reads_refresh(client):
    token, identity = make_session(last_seen_minutes=2)
    before = session(identity)
    for _ in range(3):
        response = client.get(PATH, headers=_bearer(token))
        assert response.status_code == 200, response.text
        assert response.json()["session"]["id"] == identity
        assert session(identity) == before
    assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 200
    assert session(identity)["last_seen_at"] > before["last_seen_at"]


@pytest.mark.parametrize("policy", ["idle", "absolute"])
def test_passive_status_enforces_settings_and_does_not_revive_expired_sessions(client, policy):
    token, identity = make_session(age_hours=2, last_seen_minutes=2)
    change = {"AUTH_SESSION_IDLE_MINUTES": 1} if policy == "idle" else {"AUTH_SESSION_ABSOLUTE_HOURS": 1}
    assert save(client, change).status_code == 200
    before = session(identity)
    assert client.get(PATH, headers=_bearer(token)).status_code == 401
    assert session(identity)["last_seen_at"] == before["last_seen_at"]
    assert save(client, {"AUTH_SESSION_IDLE_MINUTES": 60, "AUTH_SESSION_ABSOLUTE_HOURS": 24}).status_code == 200
    assert client.get(PATH, headers=_bearer(token)).status_code == 401


def test_passive_status_rejects_revoked_invalid_and_service_credentials(client):
    token, identity = make_session()
    with db() as connection:
        connection.execute("UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE id=%s", (identity,))
    for value in (token, "invalid", "wti_invalid"):
        assert client.get(PATH, headers=_bearer(value)).status_code == 401


def test_passive_status_preserves_required_password_change_gate(client):
    token, identity = make_session(last_seen_minutes=2)
    with db() as connection:
        connection.execute("UPDATE user_credentials SET must_change_password=true WHERE user_id=1")
    before = session(identity)
    response = client.get(PATH, headers=_bearer(token))
    assert response.status_code == 200, response.text
    assert response.json()["must_change_password"] is True
    assert session(identity) == before
