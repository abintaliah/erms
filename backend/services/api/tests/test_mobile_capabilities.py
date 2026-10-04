"""Run only through the disposable database test runner."""
from .test_messaging import account, db
from .test_global_privilege_enforcement import _bearer


def test_mobile_destinations_follow_server_availability(client, monkeypatch):
    token, _, _ = account(client, privileges=())
    path = "/api/v1/auth/me/mobile-capabilities"
    expected = ["global-search", "dashboard", "classification-browser", "favourites",
                "recent-activity", "user-profile", "sign-out"]
    response = client.get(path, headers=_bearer(token))
    assert response.status_code == 200
    assert response.json() == expected
    monkeypatch.setenv("FULL_TEXT_SEARCH_ENABLED", "false")
    assert client.get(path, headers=_bearer(token)).json() == expected[1:]


def test_mobile_capabilities_require_valid_session_and_credential_state(client):
    token, user, _ = account(client, privileges=())
    path = "/api/v1/auth/me/mobile-capabilities"
    assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    with db() as c:
        c.execute("UPDATE user_credentials SET must_change_password=true WHERE user_id=%s", (user,))
    assert client.get(path, headers=_bearer(token)).status_code == 403
