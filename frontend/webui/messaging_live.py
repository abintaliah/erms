"""Portable consumer: hints trigger durable reads; cursors are presentation checkpoints.

One instance per browser page. No shared content cache, no direct database use.
The caller persists only the cursor in API/user-scoped browser storage across logins.
"""

import asyncio
import json
import logging
import hashlib
from urllib.parse import urlsplit, urlunsplit

import httpx
from websockets.asyncio.client import connect

from .api_client import ApiError

logger = logging.getLogger(__name__)
PREFIX = "/api/v1/messages"


def mailbox_cursor_key(base_url, user_id):
    """A metadata-only checkpoint scoped to this API and account, not a login token."""
    api_namespace = hashlib.sha256(base_url.rstrip("/").encode()).hexdigest()[:24]
    return f"wathiq-message-cursor:v2:{api_namespace}:{int(user_id)}"


async def stream_events(base_url, token, transport="ws"):
    headers = {"Authorization": "Bearer " + token}
    if transport == "ws":
        url = urlsplit(base_url.rstrip("/") + PREFIX + "/stream/ws")
        uri = urlunsplit(
            ("wss" if url.scheme == "https" else "ws", url.netloc, url.path, "", "")
        )
        async with connect(
            uri,
            additional_headers=headers,
            max_size=4096,
            max_queue=16,
            open_timeout=5,
            close_timeout=2,
            ping_interval=15,
            ping_timeout=15,
        ) as socket:
            async for message in socket:
                yield json.loads(message)
    else:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=5)) as client:
            async with client.stream(
                "GET", base_url.rstrip("/") + PREFIX + "/stream/sse", headers=headers
            ) as response:
                response.raise_for_status()
                # Parse bounded chunks rather than an unbounded aiter_lines buffer.
                pending = b""
                async for chunk in response.aiter_bytes(chunk_size=1):
                    pending += chunk
                    if len(pending) > 4096:
                        raise ValueError("oversized message stream event")
                    if pending.endswith(b"\n\n"):
                        block, pending = pending, b""
                        for line in block.splitlines():
                            if line.startswith(b"data: "):
                                yield json.loads(line[6:])


class LiveMailbox:
    def __init__(self, *, api, events, load_cursor, save_cursor, present, active):
        self.api, self.events = api, events
        self.load_cursor, self.save_cursor = load_cursor, save_cursor
        self.present, self.active = present, active
        self.cursor = 0
        self.task = None
        self.lock = asyncio.Lock()

    def start(self):
        self.stop()
        self.task = asyncio.create_task(self.run(), name="messaging-page-stream")

    def stop(self):
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        self.task = None

    async def reconcile(self, *, summary):
        async with self.lock:
            total = 0
            test_total = 0
            while self.active():
                page = await self.api.request(
                    "GET",
                    PREFIX + "/catch-up",
                    params={"after": self.cursor, "limit": 50},
                )
                if not self.active():
                    return
                rows = page["items"]
                next_cursor = int(page["next_cursor"])
                if next_cursor < self.cursor or (
                    page["has_more"] and next_cursor <= self.cursor
                ):
                    raise ValueError("invalid catch-up cursor")
                total += len(rows)
                test_total += sum(bool(row.get("is_test")) for row in rows)
                if not summary:
                    for row in rows:
                        if not self.active():
                            return
                        await self.present("message", row)
                # Checkpoint each bounded page. Never advance from a transient hint.
                self.cursor = next_cursor
                await self.save_cursor(next_cursor)
                if not page["has_more"]:
                    break
            if not self.active():
                return
            unread = await self.api.request("GET", PREFIX + "/unread-count")
            if not self.active():
                return
            if summary and total:
                await self.present("summary", {"count": total, "test_count": test_total} if test_total else total)
            await self.present("unread", unread["unread_count"])
            if total:
                await self.present("refresh", None)

    async def run(self):
        try:
            value = await self.load_cursor()
            self.cursor = max(0, min(int(value or 0), 9223372036854775807))
        except asyncio.CancelledError:
            raise
        except Exception:
            # Browser storage may be unavailable during a connection transition.
            # Starting at zero is safe: durable reads remain authoritative.
            self.cursor = 0
        transport, backoff = "ws", 1
        while self.active():
            try:
                # Establish the stream BEFORE querying durable rows; subscribe
                # first then snapshot closes the startup/reconnect race.
                async for hint in self.events(transport):
                    if not self.active():
                        return
                    backoff = 1
                    kind = hint.get("event_type") if isinstance(hint, dict) else None
                    if (
                        not isinstance(hint, dict)
                        or hint.get("schema_version") != 1
                        or kind not in {"message_available", "heartbeat"}
                    ):
                        await self.reconcile(summary=True)
                    elif kind == "message_available":
                        if int(hint.get("mailbox_cursor", 0)) > self.cursor:
                            await self.reconcile(summary=False)
            except asyncio.CancelledError:
                raise
            except ApiError as error:
                if error.status_code in (401, 403):
                    return
            except Exception:
                # Unavailable optional live transport must not break the mailbox.
                logger.debug(
                    "Message stream interrupted; reconnecting with reconciliation"
                )
            if not self.active():
                return
            # During a gateway outage REST recovery still works. This also closes
            # gaps while a listener is unhealthy and before it reconnects.
            try:
                await self.reconcile(summary=True)
            except asyncio.CancelledError:
                raise
            except ApiError as error:
                if error.status_code in (401, 403):
                    return
            except Exception:
                pass
            transport = "sse" if transport == "ws" else "ws"
            await asyncio.sleep(backoff)
            backoff = min(30, backoff * 2)
