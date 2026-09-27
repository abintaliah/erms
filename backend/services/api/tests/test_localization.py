import os

import psycopg

from backend.services.api.localization import clear_catalogue_cache, localization_metrics


def test_unset_preferences_use_registry_language_and_configured_timezone(client):
    response = client.get("/api/v1/preferences")
    assert response.status_code == 200
    assert response.json() == {
        "language_tag": "en",
        "working_timezone": "Asia/Dubai",
        "direction": "ltr",
        "persisted": False,
        "version": 0,
        "date_updated": None,
    }


def test_preferences_create_update_and_bootstrap(client):
    created = client.put(
        "/api/v1/preferences",
        headers={"If-Match": "0"},
        json={"language_tag": "ar", "working_timezone": "Asia/Dubai"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["direction"] == "rtl"
    assert created.json()["version"] == 1

    bootstrap = client.get("/api/v1/i18n/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["effective_language"] == "ar"
    assert bootstrap.json()["direction"] == "rtl"
    assert bootstrap.json()["fallback_language"] == "en"
    assert "initial_messages" not in bootstrap.json()
    assert {item["language_tag"] for item in bootstrap.json()["supported_languages"]} == {"en", "ar"}
    assert bootstrap.headers["cache-control"] == "private, max-age=60"

    updated = client.put(
        "/api/v1/preferences",
        headers={"If-Match": "1"},
        json={"language_tag": "en", "working_timezone": "Europe/London"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["working_timezone"] == "Europe/London"

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        events = connection.execute(
            "SELECT operation,source FROM event_history WHERE entity_type='user_preference' ORDER BY id"
        ).fetchall()
    assert events == [("CREATE", "api"), ("UPDATE", "api")]


def test_preferences_reject_invalid_values_and_stale_writes(client):
    invalid_zone = client.put(
        "/api/v1/preferences", headers={"If-Match": "0"},
        json={"language_tag": "en", "working_timezone": "Dubai"},
    )
    assert invalid_zone.status_code == 422
    assert invalid_zone.json()["detail"]["message_key"] == "preferences.validation.working_timezone.invalid"

    unsupported = client.put(
        "/api/v1/preferences", headers={"If-Match": "0"},
        json={"language_tag": "fr", "working_timezone": "Asia/Dubai"},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["message_key"] == "preferences.validation.language.unsupported"

    assert client.put(
        "/api/v1/preferences", headers={"If-Match": "0"},
        json={"language_tag": "en", "working_timezone": "Asia/Dubai"},
    ).status_code == 200
    stale = client.put(
        "/api/v1/preferences", headers={"If-Match": "0"},
        json={"language_tag": "ar", "working_timezone": "Asia/Dubai"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"


def test_preferences_require_authentication(client):
    token = client.cookies.get("erms_session")
    client.cookies.delete("erms_session")
    try:
        assert client.get("/api/v1/preferences").status_code == 401
        assert client.get("/api/v1/i18n/bootstrap").status_code == 401
    finally:
        client.cookies.set("erms_session", token)


def test_catalogue_cache_metrics_and_health_readiness(client):
    clear_catalogue_cache("en")
    before = localization_metrics()
    first = client.get("/api/v1/i18n/catalogues/en")
    second = client.get("/api/v1/i18n/catalogues/en")
    assert first.status_code == second.status_code == 200
    assert first.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in first.headers["vary"]
    after = localization_metrics()
    assert after.get("cache_misses", 0) >= before.get("cache_misses", 0) + 1
    assert after.get("cache_hits", 0) >= before.get("cache_hits", 0) + 1
    health = client.get("/health")
    assert health.status_code == 200
    readiness = health.json()["localization"]
    assert readiness["ready"] is True
    assert readiness["default_language"] == "en"
    assert readiness["default_working_timezone"] == "Asia/Dubai"
    assert readiness["default_catalogue_etag"].startswith('"')
