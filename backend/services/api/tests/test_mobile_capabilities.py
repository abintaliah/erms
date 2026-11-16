"""Run only through the disposable database test runner."""
from .test_messaging import account, db
from .test_global_privilege_enforcement import _bearer
from .test_application_settings import save


def test_mobile_destinations_follow_server_availability(client, monkeypatch):
    administrator_token = client.cookies.get("erms_session")
    token, _, _ = account(client, privileges=())
    monkeypatch.setitem(client.headers, "Authorization", f"Bearer {administrator_token}")
    path = "/api/v1/auth/me/mobile-capabilities"
    expected = ["global-search", "dashboard", "classification-browser", "favourites",
                "recent-activity", "user-profile", "sign-out"]
    # The legacy environment must never override database ownership.
    monkeypatch.setenv("FULL_TEXT_SEARCH_ENABLED", "true")
    assert client.get(path, headers=_bearer(token)).json() == expected[1:]
    assert save(client, {"FULL_TEXT_SEARCH_ENABLED": True}).status_code == 200
    monkeypatch.setenv("FULL_TEXT_SEARCH_ENABLED", "false")
    response = client.get(path, headers=_bearer(token))
    assert response.status_code == 200
    assert response.json() == expected
    assert save(client, {"FULL_TEXT_SEARCH_ENABLED": False}).status_code == 200
    assert client.get(path, headers=_bearer(token)).json() == expected[1:]


def test_mobile_capabilities_require_valid_session_and_credential_state(client):
    token, user, _ = account(client, privileges=())
    path = "/api/v1/auth/me/mobile-capabilities"
    assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401
    with db() as c:
        c.execute("UPDATE user_credentials SET must_change_password=true WHERE user_id=%s", (user,))
    assert client.get(path, headers=_bearer(token)).status_code == 403
