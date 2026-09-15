import json
import asyncio

import httpx
import pytest

from frontend.webui.api_client import ApiError, ErmsApiClient


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
