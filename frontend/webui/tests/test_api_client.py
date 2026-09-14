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
