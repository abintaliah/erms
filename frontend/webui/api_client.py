from __future__ import annotations

import asyncio
from typing import Any

import httpx


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)

    @property
    def message(self) -> str:
        if isinstance(self.detail, dict):
            return str(self.detail.get("message", self.detail))
        return str(self.detail)


class ErmsApiClient:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30, connect=5),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiError(503, "Cannot connect to the ERMS API") from error
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text or response.reason_phrase
            raise ApiError(response.status_code, detail)
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else response.content

    async def list(self, resource: str, *, limit: int = 500, **filters: Any) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/api/v1/{resource}", params={"limit": limit, **filters}
        )

    async def get(self, resource: str, entity_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/{resource}/{entity_id}")

    async def history(self, resource: str, entity_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/api/v1/{resource}/{entity_id}/history", params={"limit": limit}
        )

    async def search_request(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/{resource}/search", json=payload)

    async def count(self, resource: str) -> int:
        result = await self.search_request(resource, {"limit": 1, "offset": 0})
        return int(result["total"])

    async def search(self, resource: str, query: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        term = query.strip()
        if not term:
            return []
        conditions = [
            {"field": field, "operator": "contains_ci", "value": term}
            for field in fields
        ]
        result = await self.request(
            "POST",
            f"/api/v1/{resource}/search",
            json={"where": {"or": conditions}, "limit": 100, "offset": 0},
        )
        return result["items"]

    async def recently_created(self, resource: str, *, limit: int = 6) -> list[dict[str, Any]]:
        result = await self.search_request(resource, {
            "sort": [{"field": "date_created", "direction": "desc"}],
            "limit": limit,
        })
        return result["items"]

    async def recently_updated(self, resource: str, *, limit: int = 6) -> list[dict[str, Any]]:
        entity_type = {"aggregations": "aggregation", "records": "record"}[resource]
        events = await self.search_request("event-history", {
            "where": {"and": [
                {"field": "entity_type", "operator": "eq", "value": entity_type},
                {"field": "operation", "operator": "eq", "value": "UPDATE"},
            ]},
            "sort": [{"field": "occurred_at", "direction": "desc"}],
            "limit": 50,
        })
        entity_ids = []
        for event in events["items"]:
            if event["entity_id"] not in entity_ids:
                entity_ids.append(event["entity_id"])
            if len(entity_ids) == limit:
                break
        results = await asyncio.gather(
            *(self.get(resource, entity_id) for entity_id in entity_ids),
            return_exceptions=True,
        )
        return [result for result in results if isinstance(result, dict)]

    async def create(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/{resource}", json=payload)

    async def update(self, resource: str, entity_id: int, version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api/v1/{resource}/{entity_id}",
            json=payload,
            headers={"If-Match": str(version)},
        )

    async def upload_component(self, record_id: int, component_order: int, name: str, content: bytes, mime_type: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/records/{record_id}/digital-components/upload",
            data={"component_order": str(component_order)},
            files={"file": (name, content, mime_type or "application/octet-stream")},
        )

    async def components(self, record_id: int) -> list[dict[str, Any]]:
        return await self.request(
            "GET", "/api/v1/digital-components", params={"record_id": record_id}
        )

    async def reorder_components(self, record_id: int, components: list[dict[str, int]]) -> None:
        await self.request("PUT", f"/api/v1/records/{record_id}/digital-components/order", json={"components": components})

    async def delete_component(self, component_id: int, version: int) -> None:
        await self.request("DELETE", f"/api/v1/digital-components/{component_id}", headers={"If-Match": str(version)})

    async def create_record_draft(self) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/record-drafts", json={})

    async def update_record_draft(self, draft_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", f"/api/v1/record-drafts/{draft_id}", json=payload)

    async def draft_components(self, draft_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/record-drafts/{draft_id}/components")

    async def upload_draft_component(self, draft_id: int, component_order: int, name: str, content: bytes, mime_type: str) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/record-drafts/{draft_id}/components",
            data={"component_order": str(component_order)},
            files={"file": (name, content, mime_type or "application/octet-stream")},
        )

    async def reorder_draft_components(self, draft_id: int, components: list[dict[str, int]]) -> None:
        await self.request("PUT", f"/api/v1/record-drafts/{draft_id}/components/order", json={"components": components})

    async def delete_draft_component(self, draft_id: int, component_id: int) -> None:
        await self.request("DELETE", f"/api/v1/record-drafts/{draft_id}/components/{component_id}")

    async def commit_record_draft(self, draft_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/record-drafts/{draft_id}/commit")

    async def discard_record_draft(self, draft_id: int) -> None:
        await self.request("DELETE", f"/api/v1/record-drafts/{draft_id}")

    async def user_roles(self, user_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/users/{user_id}/roles")

    async def role_users(self, role_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/roles/{role_id}/users")

    async def delete_assignment(self, assignment_id: int, version: int) -> None:
        await self.request(
            "DELETE",
            f"/api/v1/user-role-assignments/{assignment_id}",
            headers={"If-Match": str(version)},
        )
