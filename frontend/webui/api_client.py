from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from datetime import datetime
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
        self._transport = transport
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30, connect=5),
            transport=transport,
        )
        # A page can load dashboard cards and navigation counts concurrently.
        # Keep that burst comfortably below the API's default database pool size.
        self._request_slots = asyncio.Semaphore(4)
        self._session_token: str | None = None
        self._unauthorized_handler: Callable[[], Any] | None = None

    def set_session_token(self, token: str | None) -> None:
        """Keep authentication attached to this browser page's API client."""
        self._session_token = token

    def set_unauthorized_handler(self, handler: Callable[[], Any]) -> None:
        self._unauthorized_handler = handler

    async def close(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("X-Event-Source", "web_ui")
        if self._session_token:
            headers.setdefault("Authorization", f"Bearer {self._session_token}")
        kwargs["headers"] = headers
        try:
            async with self._request_slots:
                response = await self._client.request(method, path, **kwargs)
        except RuntimeError as error:
            if self._client.is_closed:
                raise ApiError(503, "The browser session disconnected from the ERMS API") from error
            raise
        except httpx.HTTPError as error:
            raise ApiError(503, "Cannot connect to the ERMS API") from error
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text or response.reason_phrase
            if response.status_code == 401 and self._unauthorized_handler:
                result = self._unauthorized_handler()
                if inspect.isawaitable(result):
                    await result
            raise ApiError(response.status_code, detail)
        if response.status_code == 204:
            return None
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else response.content

    async def login(self, email: str, password: str, *, user_agent: str | None = None) -> tuple[dict[str, Any], str]:
        async with httpx.AsyncClient(
            base_url=str(self._client.base_url), timeout=30, transport=self._transport
        ) as client:
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password},
                headers={
                    "X-Event-Source": "web_ui",
                    **({"User-Agent": user_agent} if user_agent else {}),
                },
            )
        if response.is_error:
            raise ApiError(response.status_code, response.json().get("detail", "login failed"))
        token = response.cookies.get("erms_session")
        if not token:
            raise ApiError(500, "authentication service did not issue a session")
        return response.json(), token

    async def me(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/auth/me")

    async def my_recent_activity(
        self, *, limit: int = 6, since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if since is not None:
            params["since"] = since.isoformat()
        return await self.request("GET", "/api/v1/auth/me/recent-activity", params=params)

    async def profile_references(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/profiles/reference", params={"limit": 500})

    async def creation_role_options(
        self, parent_aggregation_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params = (
            {"parent_aggregation_id": parent_aggregation_id}
            if parent_aggregation_id is not None else None
        )
        return await self.request("GET", "/api/v1/creation-role-options", params=params)

    async def logout(self) -> None:
        await self.request("POST", "/api/v1/auth/logout")

    async def change_password(self, current_password: str, new_password: str) -> None:
        await self.request("POST", "/api/v1/auth/change-password", json={"current_password": current_password, "new_password": new_password})

    async def login_sessions(
        self, *, user_id: int | None = None, limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params = {"offset": offset}
        if user_id is not None:
            params["user_id"] = user_id
        if limit is not None:
            params["limit"] = limit
        return await self.request("GET", "/api/v1/auth/sessions", params=params)

    async def login_sessions_page(
        self, user_id: int | None = None, *, limit: int = 20, offset: int = 0,
        query: str = "", session_status: str = "all",
        sort_by: str = "date_created", descending: bool = True,
        date_field: str = "date_created", from_timestamp: str | None = None,
        until_timestamp: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": limit, "offset": offset, "query": query,
            "session_status": session_status, "sort_by": sort_by,
            "descending": descending, "date_field": date_field,
        }
        if user_id is not None:
            params["user_id"] = user_id
        if from_timestamp:
            params["from_timestamp"] = from_timestamp
        if until_timestamp:
            params["until_timestamp"] = until_timestamp
        return await self.request(
            "GET", "/api/v1/auth/sessions/page",
            params=params,
        )

    async def revoke_session(self, session_id: int) -> None:
        await self.request("DELETE", f"/api/v1/auth/sessions/{session_id}")

    async def revoke_user_sessions(self, user_id: int) -> None:
        await self.request("DELETE", f"/api/v1/auth/users/{user_id}/sessions")

    async def issue_temporary_password(self, user_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/auth/users/{user_id}/temporary-password")

    async def service_credentials(self, user_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/users/{user_id}/api-credentials")

    async def create_service_credential(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/users/{user_id}/api-credentials", json=payload)

    async def rotate_service_credential(self, user_id: int, credential_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/users/{user_id}/api-credentials/{credential_id}/rotate", json=payload)

    async def revoke_service_credential(self, user_id: int, credential_id: int) -> None:
        await self.request("POST", f"/api/v1/users/{user_id}/api-credentials/{credential_id}/revoke")

    async def text_indexers(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/text-indexers")

    async def text_indexers_health(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/text-indexers/health")

    async def text_indexer_diagnostics(
        self, *, limit: int = 10, offset: int = 0,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", "/api/v1/text-indexers/diagnostics",
            params={"limit": limit, "offset": offset},
        )

    async def queue_text_indexers_backfill(self, batch_size: int) -> dict[str, Any]:
        return await self.request(
            "POST", "/api/v1/text-indexers/backfill", json={"batch_size": batch_size},
        )

    async def retry_failed_text_indexer_documents(self, batch_size: int) -> dict[str, Any]:
        return await self.request(
            "POST", "/api/v1/text-indexers/retry-failed", json={"batch_size": batch_size},
        )

    async def text_indexer(self, user_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/text-indexers/{user_id}")

    async def text_indexer_credentials(
        self, user_id: int, *, history: str = "all", limit: int = 5, offset: int = 0,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", f"/api/v1/text-indexers/{user_id}/credentials",
            params={"history": history, "limit": limit, "offset": offset},
        )

    async def create_text_indexer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/text-indexers", json=payload)

    async def create_text_indexer_credential(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/text-indexers/{user_id}/credentials", json=payload)

    async def rotate_text_indexer_credential(
        self, user_id: int, credential_id: int, payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/text-indexers/{user_id}/credentials/{credential_id}/rotate",
            json=payload,
        )

    async def revoke_text_indexer_credential(self, user_id: int, credential_id: int) -> None:
        await self.request(
            "POST", f"/api/v1/text-indexers/{user_id}/credentials/{credential_id}/revoke",
        )

    async def set_text_indexer_status(
        self, user_id: int, version: int, action: str,
    ) -> dict[str, Any]:
        if action not in {"activate", "suspend", "unsuspend"}:
            raise ValueError("unsupported text-indexer lifecycle action")
        return await self.request(
            "POST", f"/api/v1/text-indexers/{user_id}/{action}",
            headers={"If-Match": str(version)},
        )

    async def list(self, resource: str, *, limit: int = 500, **filters: Any) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/api/v1/{resource}", params={"limit": limit, **filters}
        )

    async def get(self, resource: str, entity_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/{resource}/{entity_id}")

    async def favourites(self) -> dict[str, list[dict[str, Any]]]:
        return await self.request("GET", "/api/v1/favourites")

    async def favourite(self, resource: str, entity_id: int) -> None:
        if resource not in {"aggregations", "records"}:
            raise ValueError("favourites support only aggregations and records")
        await self.request("PUT", f"/api/v1/favourites/{resource}/{entity_id}")

    async def unfavourite(self, resource: str, entity_id: int) -> None:
        if resource not in {"aggregations", "records"}:
            raise ValueError("favourites support only aggregations and records")
        await self.request("DELETE", f"/api/v1/favourites/{resource}/{entity_id}")

    async def browse_schemes(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/browse/classification-schemes")

    async def organization_roots(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/browse/organization/roots")

    async def organization_children(
        self, org_unit_id: int, *, include_roles: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        return await self.request(
            "GET", f"/api/v1/browse/organization/org-units/{org_unit_id}/children",
            params={"include_roles": str(include_roles).lower()},
        )

    async def organization_role_users(
        self, role_id: int, *, validity: str = "all",
    ) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/api/v1/browse/organization/roles/{role_id}/users",
            params={"validity": validity},
        )

    async def organization_summary(self, kind: str, entity_id: int) -> dict[str, Any]:
        if kind not in {"org-units", "roles"}:
            raise ValueError("organization summaries support org-units and roles")
        return await self.request(
            "GET", f"/api/v1/browse/organization/{kind}/{entity_id}/summary",
        )

    async def search_organization(
        self, query: str, *, entity_type: str = "all", status: str = "all",
    ) -> list[dict[str, Any]]:
        return await self.request(
            "GET", "/api/v1/browse/organization/search",
            params={"query": query, "entity_type": entity_type, "status": status},
        )

    async def browse_page(
        self, path: str, *, cursor: str | None = None, query: str = "", limit: int = 50,
        owning_org_unit_id: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if query:
            params["query"] = query
        if owning_org_unit_id is not None:
            params["owning_org_unit_id"] = owning_org_unit_id
        return await self.request("GET", f"/api/v1/browse/{path}", params=params)

    async def history(self, resource: str, entity_id: int, *, limit: int = 200) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/api/v1/{resource}/{entity_id}/history", params={"limit": limit}
        )

    async def permissions_catalogue(self, resource_type: str) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/permissions", params={"resource_type": resource_type})

    async def explain_access(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/authorization/explain", json=payload)

    async def holds_page(self, **params: Any) -> dict[str, Any]:
        return await self.request(
            "GET", "/api/v1/holds",
            params={key: value for key, value in params.items() if value is not None and value != ""},
        )

    async def holds(self, **params: Any) -> list[dict[str, Any]]:
        return (await self.holds_page(**params))["items"]

    async def hold(self, hold_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/holds/{hold_id}")

    async def hold_people(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/holds/people")

    async def create_hold(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/holds", json=payload)

    async def update_hold(self, hold_id: int, version: int, payload: dict[str, Any], reason: str) -> dict[str, Any]:
        return await self.request("PATCH", f"/api/v1/holds/{hold_id}", json=payload,
                                  headers={"If-Match": str(version), "X-Change-Reason": reason})

    async def delete_hold(self, hold_id: int, version: int, reason: str) -> None:
        await self.request("DELETE", f"/api/v1/holds/{hold_id}",
                           headers={"If-Match": str(version), "X-Change-Reason": reason})

    async def hold_held_items_page(self, hold_id: int, **params: Any) -> dict[str, Any]:
        return await self.request(
            "GET", f"/api/v1/holds/{hold_id}/held-items",
            params={key: value for key, value in params.items() if value is not None and value != ""},
        )

    async def hold_held_items(self, hold_id: int, **params: Any) -> list[dict[str, Any]]:
        return (await self.hold_held_items_page(hold_id, **params))["items"]

    async def hold_contributors(self, hold_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/holds/{hold_id}/contributors")

    async def replace_hold_contributors(self, hold_id: int, version: int, user_ids: list[int], reason: str) -> dict[str, Any]:
        return await self.request("PUT", f"/api/v1/holds/{hold_id}/contributors",
                                  json={"user_ids": user_ids},
                                  headers={"If-Match": str(version), "X-Change-Reason": reason})

    async def hold_history(self, hold_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/holds/{hold_id}/history", params={"limit": limit})

    async def add_hold_held_item(self, hold_id: int, resource_type: str, resource_id: int, reason: str) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/holds/{hold_id}/held-items",
                                  json={"resource_type": resource_type, "resource_id": resource_id},
                                  headers={"X-Change-Reason": reason})

    async def hold_held_item_candidates(self, hold_id: int, **params: Any) -> dict[str, Any]:
        return await self.request(
            "GET", f"/api/v1/holds/{hold_id}/held-item-candidates",
            params={key: value for key, value in params.items() if value is not None and value != ""},
        )

    async def add_hold_held_items_bulk(
        self, hold_id: int, held_items: list[dict[str, Any]], reason: str,
    ) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/holds/{hold_id}/held-items/bulk",
            json={"held_items": held_items}, headers={"X-Change-Reason": reason},
        )

    async def remove_hold_held_item(self, hold_id: int, resource_type: str, resource_id: int, version: int, reason: str) -> None:
        await self.request("DELETE", f"/api/v1/holds/{hold_id}/held-items/{resource_type}/{resource_id}",
                           headers={"If-Match": str(version), "X-Change-Reason": reason})

    async def remove_hold_held_items_bulk(self, hold_id: int, held_items: list[dict[str, Any]], reason: str) -> dict[str, Any]:
        return await self.request("POST",f"/api/v1/holds/{hold_id}/held-items/bulk-remove",
                                  json={"held_items":held_items},headers={"X-Change-Reason":reason})

    async def effective_holds(self, resource_type: str, resource_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/{resource_type}s/{resource_id}/effective-holds")

    async def add_resource_to_hold(self, resource_type: str, resource_id: int, hold_id: int, reason: str) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/{resource_type}s/{resource_id}/holds",
                                  json={"hold_id": hold_id}, headers={"X-Change-Reason": reason})

    async def remove_resource_from_hold(self, resource_type: str, resource_id: int, hold_id: int, reason: str) -> dict[str, Any]:
        return await self.request("DELETE", f"/api/v1/{resource_type}s/{resource_id}/holds/{hold_id}",
                                  headers={"X-Change-Reason": reason})

    async def remove_all_direct_holds(self, resource_type: str, resource_id: int, reason: str) -> dict[str, Any]:
        return await self.request("DELETE", f"/api/v1/{resource_type}s/{resource_id}/holds",
                                  headers={"X-Change-Reason": reason})

    async def explainable_users(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/authorization/explainable-users")

    async def governance_custody(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/authorization/governance-custody")

    async def security_summary(
        self, *, hours: int = 24, start_at: str | None = None, end_at: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"hours": hours}
        if start_at:
            params["start_at"] = start_at
        if end_at:
            params["end_at"] = end_at
        return await self.request("GET", "/api/v1/security-operations/summary", params=params)

    async def security_reconciliation(self) -> dict[str, Any]:
        return await self.request("GET", "/api/v1/security-operations/reconciliation")

    async def resource_acl(self, resource: str, entity_id: int) -> dict[str, Any]:
        result = await self.request("GET", f"/api/v1/{resource}/{entity_id}/permissions")
        # Normalize the resource endpoint's explicit effective-source names to
        # the common source keys consumed by ACL presentation components.
        result["source"] = result.get("effective_acl_source")
        result["source_resource_id"] = result.get("effective_acl_source_id")
        return result

    async def resource_capabilities(self, resource: str, entity_id: int) -> dict[str, bool]:
        response = await self.request(
            "GET", f"/api/v1/{resource}/{entity_id}/capabilities",
        )
        return response["capabilities"]

    async def change_vital_status(self, resource: str, entity_id: int, version: int, is_vital: bool, reason: str) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/{resource}/{entity_id}/vital-status",
            json={"is_vital": is_vital, "reason": reason}, headers={"If-Match": str(version)},
        )

    async def change_review_date(self, resource: str, entity_id: int, version: int, date_of_next_review: str | None, reason: str) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/{resource}/{entity_id}/review-date",
            json={"date_of_next_review": date_of_next_review, "reason": reason},
            headers={"If-Match": str(version)},
        )

    async def change_aggregation_location(self, entity_id: int, version: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/aggregations/{entity_id}/location", json=payload, headers={"If-Match": str(version)})

    async def preview_aggregation_location(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/aggregations/{entity_id}/location-preview", json=payload)

    async def acl_move_preview(
        self, resource: str, entity_id: int, destination_aggregation_id: int,
        *, keep_current_access_as_override: bool = False,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", f"/api/v1/{resource}/{entity_id}/acl-move-preview",
            params={
                "destination_aggregation_id": destination_aggregation_id,
                "keep_current_access_as_override": str(keep_current_access_as_override).lower(),
            },
        )

    async def move_with_acl(
        self, resource: str, entity_id: int, payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/{resource}/{entity_id}/acl-move", json=payload,
        )

    async def ownership_correction_options(self) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/ownership-correction-options")

    async def ownership_correction_preview(
        self, aggregation_id: int, destination_role_id: int,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", f"/api/v1/aggregations/{aggregation_id}/ownership-correction-preview",
            params={"destination_role_id": destination_role_id},
        )

    async def correct_ownership(
        self, aggregation_id: int, destination_role_id: int, reason: str,
    ) -> dict[str, Any]:
        return await self.request(
            "POST", f"/api/v1/aggregations/{aggregation_id}/correct-ownership",
            json={"destination_role_id": destination_role_id, "reason": reason},
        )

    async def replace_resource_acl(self, resource: str, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PUT", f"/api/v1/{resource}/{entity_id}/permissions", json=payload)

    async def child_acl(self, aggregation_id: int, child_type: str) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/aggregations/{aggregation_id}/default-child-{child_type}-permissions")

    async def replace_child_acl(self, aggregation_id: int, child_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PUT", f"/api/v1/aggregations/{aggregation_id}/default-child-{child_type}-permissions", json=payload)

    async def preview_child_acl(self, aggregation_id: int, child_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/aggregations/{aggregation_id}/default-child-{child_type}-permissions/preview", json=payload)

    async def event_history_operations(self) -> list[str]:
        return await self.request("GET", "/api/v1/event-history/operations")

    async def event_history_filter_options(self) -> dict[str, list[str]]:
        return await self.request("GET", "/api/v1/event-history/filter-options")

    async def search_request(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/{resource}/search", json=payload)

    async def full_text_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/v1/full-text-search", json=payload)

    async def count(self, resource: str) -> int:
        result = await self.search_request(resource, {"limit": 1, "offset": 0})
        return int(result["total"])

    async def dashboard_summary(
        self, *, recent_limit: int, recent_since: datetime,
    ) -> dict[str, Any]:
        return await self.request(
            "GET", "/api/v1/dashboard/summary",
            params={
                "recent_limit": recent_limit,
                "recent_since": recent_since.isoformat(),
            },
        )

    async def dashboard_reviews(self, state: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            page = await self.request(
                "GET", "/api/v1/dashboard/reviews",
                params={"state": state, "limit": 500, "offset": len(rows)},
            )
            rows.extend(page)
            if len(page) < 500:
                return rows

    async def search(
        self, resource: str, query: str, fields: tuple[str, ...],
        *, owning_org_unit_id: int | None = None,
    ) -> list[dict[str, Any]]:
        term = query.strip()
        if not term:
            return []
        conditions = [
            {"field": field, "operator": "contains_ci", "value": term}
            for field in fields
        ]
        where: dict[str, Any] = {"or": conditions}
        if owning_org_unit_id is not None and resource in {"aggregations", "records"}:
            where = {"and": [
                where,
                {
                    "field": "owning_org_unit_id", "operator": "eq",
                    "value": owning_org_unit_id,
                },
            ]}
        result = await self.request(
            "POST",
            f"/api/v1/{resource}/search",
            json={"where": where, "limit": 100, "offset": 0},
        )
        return result["items"]

    async def _recent_entities_from_events(
        self,
        resource: str,
        operation: str,
        actor_user_id: int | None,
        limit: int,
        since: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        entity_type = {
            "aggregations": "aggregation",
            "records": "record",
            "classifications": "classification",
        }[resource]
        conditions: list[dict[str, Any]] = [
            {"field": "entity_type", "operator": "eq", "value": entity_type},
            {"field": "operation", "operator": "eq", "value": operation},
        ]
        if actor_user_id is not None:
            conditions.append(
                {"field": "actor_user_id", "operator": "eq", "value": actor_user_id}
            )
        if since is not None:
            conditions.append({
                "field": "occurred_at",
                "operator": "gte",
                "value": since.isoformat() if isinstance(since, datetime) else since,
            })
        events = await self.search_request("event-history", {
            "where": {"and": conditions},
            "sort": [{"field": "occurred_at", "direction": "desc"}],
            "limit": 200,
        })
        entity_ids = []
        activity_times: dict[int, str] = {}
        for event in events["items"]:
            if event["entity_id"] not in entity_ids:
                entity_ids.append(event["entity_id"])
                activity_times[event["entity_id"]] = event["occurred_at"]
            if len(entity_ids) == limit:
                break
        results = await asyncio.gather(
            *(self.get(resource, entity_id) for entity_id in entity_ids),
            return_exceptions=True,
        )
        return [
            {**result, "_activity_at": activity_times[entity_id]}
            for entity_id, result in zip(entity_ids, results)
            if isinstance(result, dict)
        ]

    async def _recent_entities_from_my_activity(
        self,
        resource: str,
        operation: str,
        limit: int,
        since: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        entity_type = {"aggregations": "aggregation", "records": "record"}[resource]
        parsed_since = (
            since if isinstance(since, datetime)
            else datetime.fromisoformat(since.replace("Z", "+00:00")) if since
            else None
        )
        activity = await self.my_recent_activity(limit=limit, since=parsed_since)
        entries = [
            item for item in activity
            if item["entity_type"] == entity_type and item["operation"] == operation
        ][:limit]
        results = await asyncio.gather(
            *(self.get(resource, entry["entity_id"]) for entry in entries),
            return_exceptions=True,
        )
        return [
            {**result, "_activity_at": entry["occurred_at"]}
            for entry, result in zip(entries, results)
            if isinstance(result, dict)
        ]

    async def recently_created(
        self, resource: str, *, limit: int = 6, actor_user_id: int | None = None,
        since: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        if actor_user_id is not None:
            return await self._recent_entities_from_events(
                resource, "CREATE", actor_user_id, limit, since,
            )
        result = await self.search_request(resource, {
            "sort": [{"field": "date_created", "direction": "desc"}],
            "limit": limit,
        })
        return result["items"]

    async def recently_updated(
        self, resource: str, *, limit: int = 6, actor_user_id: int | None = None,
        since: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        if actor_user_id is not None:
            return await self._recent_entities_from_events(
                resource, "UPDATE", actor_user_id, limit, since,
            )
        if resource in {"aggregations", "records"}:
            return await self._recent_entities_from_my_activity(
                resource, "UPDATE", limit, since,
            )
        result = await self.search_request(resource, {
            "sort": [{"field": "date_updated", "direction": "desc"}],
            "limit": limit,
        })
        return result["items"]

    async def create(self, resource: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/{resource}", json=payload)

    async def update(
        self, resource: str, entity_id: int, version: int, payload: dict[str, Any],
        *, change_reason: str | None = None,
    ) -> dict[str, Any]:
        headers = {"If-Match": str(version)}
        if change_reason:
            headers["X-Change-Reason"] = change_reason
        return await self.request(
            "PATCH",
            f"/api/v1/{resource}/{entity_id}",
            json=payload,
            headers=headers,
        )

    async def delete(
        self, resource: str, entity_id: int, version: int, *, reason: str | None = None,
    ) -> None:
        headers = {"If-Match": str(version)}
        if reason:
            headers["X-Change-Reason"] = reason
        await self.request(
            "DELETE",
            f"/api/v1/{resource}/{entity_id}",
            headers=headers,
        )

    async def deletion_preflight(self, resource: str, entity_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/{resource}/{entity_id}/deletion-preflight")

    async def preview_security_level_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "POST", "/api/v1/security-level-changes/preview", json=payload,
        )

    async def apply_security_level_change(
        self, payload: dict[str, Any], *, reason: str,
    ) -> dict[str, Any]:
        return await self.request(
            "POST", "/api/v1/security-level-changes/apply", json=payload,
            headers={"X-Change-Reason": reason},
        )

    async def profile_privileges(self, profile_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/profiles/{profile_id}/privileges")

    async def profile_impact(self, profile_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/profiles/{profile_id}/impact")

    async def replace_profile_privileges(
        self, profile_id: int, version: int, privilege_ids: list[int], *, reason: str,
    ) -> dict[str, Any]:
        return await self.request(
            "PUT", f"/api/v1/profiles/{profile_id}/privileges",
            json={"privilege_ids": privilege_ids},
            headers={"If-Match": str(version), "X-Change-Reason": reason},
        )

    async def set_active(
        self, resource: str, entity_id: int, version: int, *, active: bool,
    ) -> dict[str, Any]:
        action = "activate" if active else "deactivate"
        return await self.request(
            "POST", f"/api/v1/{resource}/{entity_id}/{action}",
            headers={"If-Match": str(version)},
        )

    async def set_user_suspended(
        self, user_id: int, version: int, *, suspended: bool,
    ) -> dict[str, Any]:
        action = "suspend" if suspended else "unsuspend"
        return await self.request(
            "POST", f"/api/v1/users/{user_id}/{action}",
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

    async def download_component(self, component_id: int) -> bytes:
        return await self.request("GET", f"/api/v1/digital-components/{component_id}/content")

    async def view_component_pdf(self, component_id: int) -> bytes:
        return await self.request("GET", f"/api/v1/digital-components/{component_id}/rendition")

    async def print_component_pdf(self, component_id: int) -> bytes:
        return await self.request("GET", f"/api/v1/digital-components/{component_id}/print-rendition")

    async def reindex_component(self, component_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/digital-components/{component_id}/reindex")

    async def reindex_record(self, record_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/records/{record_id}/reindex")

    async def indexing_status(self, status_url: str) -> dict[str, Any]:
        return await self.request("GET", status_url)

    async def component_indexing_status(self, component_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/digital-components/{component_id}/indexing-status")

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

    async def commit_record_draft(
        self, draft_id: int, creator_acl_role_id: int | None = None,
    ) -> dict[str, Any]:
        params = (
            {"creator_acl_role_id": creator_acl_role_id}
            if creator_acl_role_id is not None else None
        )
        return await self.request(
            "POST", f"/api/v1/record-drafts/{draft_id}/commit", params=params,
        )

    async def discard_record_draft(self, draft_id: int) -> None:
        await self.request("DELETE", f"/api/v1/record-drafts/{draft_id}")

    async def recent_classifications(self, limit: int = 4) -> list[dict[str, Any]]:
        return await self.request("GET", "/api/v1/classifications/recent", params={"limit": limit})

    async def classification_path(self, classification_id: int) -> list[dict[str, Any]]:
        return await self.request("GET", f"/api/v1/classifications/{classification_id}/path")

    async def effective_retention_rule(self, aggregation_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/aggregations/{aggregation_id}/effective-retention-rule")

    async def aggregation_retention_rule(self, aggregation_id: int) -> dict[str, Any] | None:
        return await self.request("GET", f"/api/v1/aggregations/{aggregation_id}/retention-rule")

    async def put_aggregation_retention_rule(
        self, aggregation_id: int, payload: dict[str, Any], version: int | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "PUT", f"/api/v1/aggregations/{aggregation_id}/retention-rule",
            params={"version": version} if version else {}, json=payload,
            headers={"X-Change-Reason": payload["justification"]},
        )

    async def delete_aggregation_retention_rule(
        self, aggregation_id: int, version: int, reason: str,
    ) -> None:
        await self.request(
            "DELETE", f"/api/v1/aggregations/{aggregation_id}/retention-rule",
            headers={"If-Match": str(version), "X-Change-Reason": reason},
        )

    async def classification_effective_rule(self, classification_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/classifications/{classification_id}/effective-retention-rule")

    async def classification_retention_rule(self, classification_id: int) -> dict[str, Any] | None:
        return await self.request("GET", f"/api/v1/classifications/{classification_id}/retention-rule")

    async def put_classification_retention_rule(
        self, classification_id: int, payload: dict[str, Any], version: int | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "PUT", f"/api/v1/classifications/{classification_id}/retention-rule",
            params={"version": version} if version else {}, json=payload,
        )

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
