from __future__ import annotations

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

    async def list(self, resource: str) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/{resource}")

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
