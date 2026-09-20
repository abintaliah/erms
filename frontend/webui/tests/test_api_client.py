import json
import asyncio

import httpx
import pytest

from frontend.webui.api_client import ApiError, ErmsApiClient


def test_api_client_bounds_concurrent_page_requests():
    active = 0
    maximum_active = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"ok": True})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await asyncio.gather(*(
                client.request("GET", f"/request/{index}") for index in range(20)
            ))
        finally:
            await client.close()

    asyncio.run(exercise())
    assert maximum_active == 4


def test_search_builds_controlled_or_grammar():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"items": [{"id": 4}], "total": 1})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.search("records", "annual", ("record_number", "title"))
        finally:
            await client.close()

    rows = asyncio.run(exercise())

    assert rows == [{"id": 4}]
    assert captured["path"] == "/api/v1/records/search"
    assert captured["body"]["where"] == {
        "or": [
            {"field": "record_number", "operator": "contains_ci", "value": "annual"},
            {"field": "title", "operator": "contains_ci", "value": "annual"},
        ]
    }


def test_classification_search_uses_literal_case_insensitive_containment():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"items": [], "total": 0})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.search("classifications", "finance", ("code", "title"))
        finally:
            await client.close()

    asyncio.run(exercise())
    assert captured["body"]["where"]["or"][0] == {
        "field": "code", "operator": "contains_ci", "value": "finance",
    }


def test_event_history_operations_uses_authoritative_filter_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=["AUTHENTICATION_SUCCEEDED", "CREATE"])

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.event_history_operations()
        finally:
            await client.close()

    assert asyncio.run(exercise()) == ["AUTHENTICATION_SUCCEEDED", "CREATE"]
    assert captured["path"] == "/api/v1/event-history/operations"


def test_event_history_filter_options_uses_authoritative_filter_endpoint():
    captured = {}
    expected = {
        "entity_types": ["aggregation", "user"],
        "operations": ["AUTHENTICATION_SUCCEEDED", "CREATE"],
        "sources": ["api", "web_ui"],
        "actor_types": ["automated_process", "user"],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        return httpx.Response(200, json=expected)

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.event_history_filter_options()
        finally:
            await client.close()

    assert asyncio.run(exercise()) == expected
    assert captured["path"] == "/api/v1/event-history/filter-options"


def test_my_recent_activity_uses_the_self_only_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.my_recent_activity(limit=5)
        finally:
            await client.close()

    assert asyncio.run(exercise()) == []
    assert captured == {
        "path": "/api/v1/auth/me/recent-activity",
        "params": {"limit": "5"},
    }


def test_resource_acl_normalizes_the_real_api_source_contract():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/records/19/permissions"
        return httpx.Response(200, json={
            "inherit_acl_from_parent": True,
            "effective_acl_source": "parent_default",
            "effective_acl_source_id": 184,
            "effective_acl": [], "override_acl": [],
            "override_acl_is_dormant": True, "resource_acl_version": 3,
        })

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.resource_acl("records", 19)
        finally:
            await client.close()

    result = asyncio.run(exercise())
    assert result["source"] == "parent_default"
    assert result["source_resource_id"] == 184


def test_browse_page_preserves_opaque_cursor_and_scoped_filter():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": [], "next_cursor": None, "total": 0})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.browse_page(
                "aggregations/8/records", cursor="opaque-token", query="annual", limit=25,
            )
        finally:
            await client.close()

    result = asyncio.run(exercise())
    assert result["total"] == 0
    assert captured["path"] == "/api/v1/browse/aggregations/8/records"
    assert captured["params"] == {
        "limit": "25", "cursor": "opaque-token", "query": "annual",
    }


def test_personal_classification_recent_activity_uses_audit_events():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        requests.append((request.method, request.url.path, body))
        if request.url.path == "/api/v1/event-history/search":
            return httpx.Response(200, json={
                "items": [{"entity_id": 9, "occurred_at": "2026-09-16T10:00:00Z"}],
                "total": 1,
            })
        return httpx.Response(200, json={"id": 9, "code": "FIN", "title": "Finance"})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.recently_created(
                "classifications", actor_user_id=4, limit=4,
            )
        finally:
            await client.close()

    rows = asyncio.run(exercise())
    assert rows[0]["id"] == 9
    event_request = requests[0][2]
    assert {"field": "entity_type", "operator": "eq", "value": "classification"} in event_request["where"]["and"]
    assert {"field": "actor_user_id", "operator": "eq", "value": 4} in event_request["where"]["and"]


def test_update_sends_if_match_version():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["if_match"] = request.headers["if-match"]
        return httpx.Response(200, json={"id": 7, "version": 4})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.update("users", 7, 3, {"name": "New name"})
        finally:
            await client.close()

    result = asyncio.run(exercise())

    assert captured["if_match"] == "3"
    assert result["version"] == 4


def test_webui_requests_identify_their_event_source():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["source"] = request.headers.get("x-event-source")
        return httpx.Response(200, json={"items": [], "total": 0})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.count("records")
        finally:
            await client.close()

    asyncio.run(exercise())
    assert captured["source"] == "web_ui"


def test_delete_sends_if_match_version():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(method=request.method, path=request.url.path, version=request.headers["if-match"])
        return httpx.Response(204)

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.delete("records", 17, 6)
        finally:
            await client.close()

    asyncio.run(exercise())
    assert captured == {"method": "DELETE", "path": "/api/v1/records/17", "version": "6"}


def test_favourite_client_uses_expected_routes():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"aggregations": [], "records": []})
        return httpx.Response(204)

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.favourites()
            await client.favourite("aggregations", 7)
            await client.unfavourite("records", 8)
            with pytest.raises(ValueError):
                await client.favourite("users", 9)
        finally:
            await client.close()

    asyncio.run(exercise())
    assert requests == [
        ("GET", "/api/v1/favourites"),
        ("PUT", "/api/v1/favourites/aggregations/7"),
        ("DELETE", "/api/v1/favourites/records/8"),
    ]


def test_api_error_preserves_conflict_details():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            412,
            json={"detail": {"message": "entity has changed", "current_version": 9}},
        )

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.update("records", 2, 8, {"title": "Stale"})
        finally:
            await client.close()

    with pytest.raises(ApiError) as caught:
        asyncio.run(exercise())

    assert caught.value.status_code == 412
    assert caught.value.detail["current_version"] == 9


def test_membership_navigation_and_delete_use_expected_routes():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.headers.get("if-match")))
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=[])

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.user_roles(4)
            await client.role_users(8)
            await client.delete_assignment(12, 3)
        finally:
            await client.close()

    asyncio.run(exercise())
    assert requests == [
        ("GET", "/api/v1/users/4/roles", None),
        ("GET", "/api/v1/roles/8/users", None),
        ("DELETE", "/api/v1/user-role-assignments/12", "3"),
    ]


def test_recently_created_uses_date_sort():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"items": [{"id": 9}], "total": 1})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.recently_created("aggregations")
        finally:
            await client.close()

    assert asyncio.run(exercise()) == [{"id": 9}]
    assert captured["sort"] == [{"field": "date_created", "direction": "desc"}]


def test_recently_updated_uses_self_activity_without_audit_access():
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/auth/me/recent-activity":
            return httpx.Response(200, json=[{
                "entity_type": "record", "entity_id": 11,
                "operation": "UPDATE", "occurred_at": "2026-09-20T08:00:00Z",
            }])
        assert request.url.path == "/api/v1/records/11"
        return httpx.Response(200, json={"id": 11, "title": "Visible record"})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.recently_updated("records")
        finally:
            await client.close()

    assert asyncio.run(exercise()) == [{
        "id": 11, "title": "Visible record",
        "_activity_at": "2026-09-20T08:00:00Z",
    }]
    assert requests == [
        "/api/v1/auth/me/recent-activity", "/api/v1/records/11",
    ]


@pytest.mark.parametrize(
    ("method_name", "operation"),
    (("recently_created", "CREATE"), ("recently_updated", "UPDATE")),
)
def test_personal_recent_activity_filters_audit_events_by_current_user(
    method_name, operation,
):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/event-history/search":
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "items": [{"entity_id": 9, "occurred_at": "2026-09-16T01:02:03Z"}],
                    "total": 1,
                },
            )
        assert request.url.path == "/api/v1/records/9"
        return httpx.Response(200, json={"id": 9, "title": "Mine"})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            method = getattr(client, method_name)
            return await method(
                "records", actor_user_id=42, since="2026-08-17T00:00:00+00:00"
            )
        finally:
            await client.close()

    assert asyncio.run(exercise()) == [{
        "id": 9,
        "title": "Mine",
        "_activity_at": "2026-09-16T01:02:03Z",
    }]
    assert captured["where"]["and"] == [
        {"field": "entity_type", "operator": "eq", "value": "record"},
        {"field": "operation", "operator": "eq", "value": operation},
        {"field": "actor_user_id", "operator": "eq", "value": 42},
        {
            "field": "occurred_at",
            "operator": "gte",
            "value": "2026-08-17T00:00:00+00:00",
        },
    ]


def test_count_uses_search_total_without_loading_all_rows():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"items": [{"id": 1}], "total": 417})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.count("records")
        finally:
            await client.close()

    assert asyncio.run(exercise()) == 417
    assert captured == {
        "path": "/api/v1/records/search",
        "body": {"limit": 1, "offset": 0},
    }


def test_login_extracts_opaque_cookie_and_forwards_browser_identity():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["user_agent"] = request.headers["user-agent"]
        return httpx.Response(
            200,
            json={"user": {"id": 1}, "roles": [], "session": {"id": 2}, "must_change_password": False},
            headers={"set-cookie": "erms_session=opaque-token; HttpOnly; Path=/; SameSite=Lax"},
        )

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.login("user@example.org", "secret", user_agent="Browser/Test")
        finally:
            await client.close()

    principal, token = asyncio.run(exercise())
    assert principal["user"]["id"] == 1
    assert token == "opaque-token"
    assert captured["user_agent"] == "Browser/Test"


def test_page_scoped_token_survives_parallel_background_requests():
    authorization_headers = []

    async def handler(request: httpx.Request) -> httpx.Response:
        authorization_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"items": [], "total": 0})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        client.set_session_token("page-specific-token")
        try:
            await asyncio.gather(client.count("records"), client.count("aggregations"))
        finally:
            await client.close()

    asyncio.run(exercise())
    assert authorization_headers == ["Bearer page-specific-token"] * 2


def test_unauthorized_response_clears_page_through_handler():
    handled = []

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "authentication required"})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        client.set_session_token("expired-token")
        client.set_unauthorized_handler(lambda: handled.append(True))
        try:
            with pytest.raises(ApiError):
                await client.me()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert handled == [True]


def test_component_download_and_view_use_distinct_content_routes():
    paths = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, content=b"document", headers={"content-type": "application/pdf"})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            assert await client.download_component(8) == b"document"
            assert await client.view_component_pdf(8) == b"document"
        finally:
            await client.close()

    asyncio.run(exercise())
    assert paths == [
        "/api/v1/digital-components/8/content",
        "/api/v1/digital-components/8/rendition",
    ]


def test_entity_history_uses_read_only_timeline_route():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["limit"] = request.url.params["limit"]
        return httpx.Response(200, json=[{"id": 1, "operation": "CREATE"}])

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            return await client.history("records", 42)
        finally:
            await client.close()

    assert asyncio.run(exercise())[0]["operation"] == "CREATE"
    assert captured == {
        "method": "GET",
        "path": "/api/v1/records/42/history",
        "limit": "200",
    }


def test_authorization_ui_client_uses_explanation_and_custody_endpoints():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=[] if request.url.path.endswith("explainable-users") else {})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.explain_access({"resource_type": "record", "resource_id": 1, "operation": "record.view"})
            await client.explainable_users()
            await client.governance_custody()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert seen == [
        ("POST", "/api/v1/authorization/explain"),
        ("GET", "/api/v1/authorization/explainable-users"),
        ("GET", "/api/v1/authorization/governance-custody"),
    ]


def test_security_operations_client_routes_are_read_only():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={})

    async def exercise():
        client = ErmsApiClient("http://api.test", transport=httpx.MockTransport(handler))
        try:
            await client.security_summary(hours=48)
            await client.security_reconciliation()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert seen == [
        ("GET", "/api/v1/security-operations/summary", {"hours": "48"}),
        ("GET", "/api/v1/security-operations/reconciliation", {}),
    ]
