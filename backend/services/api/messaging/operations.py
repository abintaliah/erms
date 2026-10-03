"""Content-free operational measurements and bounded retention worker."""

import asyncio
from contextlib import suppress
from time import monotonic
from uuid import uuid4
import logging
import threading
from psycopg.errors import (
    LockNotAvailable,
    QueryCanceled,
    SerializationFailure,
    DeadlockDetected,
)
from ..database import pool
from .config import LIMITS
from .retention import purge_group, cleanup_drafts

logger = logging.getLogger(__name__)
METRICS = frozenset(
    (
        "send_success",
        "send_failure",
        "fanout_count",
        "notifications_emitted",
        "catchup_failure",
        "restricted_count",
        "capture_failure",
        "capture_seconds",
        "cleanup_failure",
        "cleanup_seconds",
        "purged_messages",
        "purged_groups",
        "purged_drafts",
        "group_size",
        "delayed_groups",
        "system_failure",
        "system_seconds",
        "test_success",
        "test_failure",
        "test_rate_rejected",
        "test_seconds",
    )
)


def observe(
    metric, value=1, producer="", *, connection=None, failure=False, resolve=False
):
    if metric not in METRICS:
        raise ValueError("Unknown operational metric")

    def write(c):
        c.execute(
            """INSERT INTO messaging_operational_metrics(metric,producer_code,value,observations,unresolved_since)
 VALUES(%s,%s,%s,1,CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END)
 ON CONFLICT(metric,instance_id,producer_code) DO UPDATE SET value=messaging_operational_metrics.value+EXCLUDED.value,
 observations=messaging_operational_metrics.observations+1,last_observed_at=CURRENT_TIMESTAMP,
 unresolved_since=CASE WHEN %s THEN NULL ELSE COALESCE(messaging_operational_metrics.unresolved_since,EXCLUDED.unresolved_since) END""",
            (metric, producer, value, failure, resolve),
        )

    if connection is not None:
        write(connection)
    else:
        try:
            with pool.connection() as c:
                c.execute("SET LOCAL lock_timeout='100ms'")
                write(c)
        except Exception:
            logger.warning("messaging_metric_write_failed metric=%s", metric)


def resolved(metric, producer="", connection=None):
    def write(c):
        c.execute(
            "UPDATE messaging_operational_metrics SET unresolved_since=NULL WHERE metric=%s AND producer_code=%s",
            (metric, producer),
        )

    if connection is not None:
        write(connection)
    else:
        try:
            with pool.connection() as c:
                c.execute("SET LOCAL lock_timeout='100ms'")
                write(c)
        except Exception:
            logger.warning("messaging_metric_resolution_failed metric=%s", metric)


def cleanup_page(after=None, stop=None):
    with pool.connection() as c:
        candidates = c.execute(
            """SELECT id FROM message_envelopes WHERE expires_at<=CURRENT_TIMESTAMP
 AND (%s::uuid IS NULL OR id>%s) ORDER BY id LIMIT %s""",
            (after, after, LIMITS["CLEANUP_BATCH_SIZE"]),
        ).fetchall()
        count = cleanup_drafts(c)
        observe("purged_drafts", count, connection=c)
    candidate_ids = [row["id"] for row in candidates]
    covered = set()
    for candidate in candidates:
        if candidate["id"] in covered:
            continue
        if stop and stop.is_set():
            break
        start = monotonic()
        snapshot = {}
        try:
            with pool.connection() as c:
                count = purge_group(c, candidate["id"], snapshot)
                size = c.execute(
                    "SELECT count(*) AS n FROM messaging_purge_candidates"
                ).fetchone()["n"]
                covered.update(
                    row["id"]
                    for row in c.execute(
                        "SELECT id FROM messaging_purge_candidates WHERE id=ANY(%s::uuid[])",
                        (candidate_ids,),
                    )
                )
                observe("group_size", size, connection=c)
                if count:
                    observe("purged_messages", count, connection=c)
                    observe("purged_groups", connection=c)
                elif size > LIMITS["CLEANUP_BATCH_SIZE"]:
                    observe("delayed_groups", connection=c)
            observe("cleanup_seconds", monotonic() - start)
            resolved("cleanup_failure")
        except (
            LockNotAvailable,
            QueryCanceled,
            SerializationFailure,
            DeadlockDetected,
        ):
            observe("cleanup_failure", failure=True)
            group_failed(snapshot)
        except Exception:
            observe("cleanup_failure", failure=True)
            group_failed(snapshot)
            logger.warning("messaging_cleanup_failed envelope_id=%s", candidate["id"])
    return (
        candidates[-1]["id"]
        if len(candidates) == LIMITS["CLEANUP_BATCH_SIZE"]
        else None
    )


def group_failed(snapshot):
    if not snapshot:
        return
    try:
        with pool.connection() as c:
            c.execute(
                """INSERT INTO messaging_cleanup_groups(group_key,member_count,expired_count,eligible_at,failure_count,oldest_failure_at)
 VALUES(%s,%s,%s,%s,1,CURRENT_TIMESTAMP) ON CONFLICT(group_key) DO UPDATE SET failure_count=messaging_cleanup_groups.failure_count+1,
 oldest_failure_at=COALESCE(messaging_cleanup_groups.oldest_failure_at,CURRENT_TIMESTAMP)""",
                tuple(
                    snapshot[k]
                    for k in (
                        "group_key",
                        "member_count",
                        "expired_count",
                        "eligible_at",
                    )
                ),
            )
    except Exception:
        logger.warning("messaging_group_failure_metric_unavailable")


class Worker:
    def __init__(self, gateway):
        self.gateway = gateway
        self.instance_id = uuid4()
        self.task = None
        self.stopping = threading.Event()
        self.wake = asyncio.Event()

    def start(self):
        self.task = asyncio.create_task(self.loop(), name="messaging-lifecycle")

    def snapshot(self):
        data = self.gateway.operational_health()
        with pool.connection() as c:
            c.execute(
                """INSERT INTO messaging_gateway_health VALUES(%s,CURRENT_TIMESTAMP,%s,%s,%s,%s,%s,%s)
 ON CONFLICT(instance_id) DO UPDATE SET observed_at=EXCLUDED.observed_at,listener_connected=EXCLUDED.listener_connected,
 listener_generation=EXCLUDED.listener_generation,notifications_received=EXCLUDED.notifications_received,last_notification_at=EXCLUDED.last_notification_at,
 active_connections=EXCLUDED.active_connections,slow_disconnects=EXCLUDED.slow_disconnects""",
                (
                    self.instance_id,
                    data["listener_connected"],
                    data["listener_generation"],
                    data["notifications_received"],
                    data["last_notification_at"],
                    data["active_connections"],
                    data["slow_disconnects"],
                ),
            )

    async def loop(self):
        next_cleanup = monotonic() + LIMITS["CLEANUP_INTERVAL_SECONDS"]
        after = None
        next_hold_reminder = monotonic()
        while not self.stopping.is_set():
            try:
                await asyncio.to_thread(self.snapshot)
                if monotonic() >= next_hold_reminder:
                    from ..hold_notifications import reminder_tick
                    next_hold_reminder = monotonic() + 60
                    try:
                        await asyncio.to_thread(reminder_tick)
                    except Exception:
                        logger.warning("legal_hold_notification_worker_failed")
                if monotonic() >= next_cleanup:
                    after = await asyncio.to_thread(cleanup_page, after, self.stopping)
                    next_cleanup = monotonic() + (
                        1 if after else LIMITS["CLEANUP_INTERVAL_SECONDS"]
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("messaging_lifecycle_worker_failed")
            try:
                await asyncio.wait_for(self.wake.wait(), 15)
            except asyncio.TimeoutError:
                pass

    async def stop(self):
        if self.task:
            self.stopping.set()
            self.wake.set()
            await self.task

        def remove():
            with pool.connection() as c:
                c.execute(
                    "DELETE FROM messaging_gateway_health WHERE instance_id=%s",
                    (self.instance_id,),
                )

        await asyncio.to_thread(remove)


def measure_system(function):
    from functools import wraps

    @wraps(function)
    def measured(*args, **kwargs):
        start = monotonic()
        producer = kwargs.get("producer_code", "")
        # Never turn unregistered caller input into a metric label.
        from .notification_registry import registry

        producer = producer if producer in registry.definitions else ""
        try:
            result = function(*args, **kwargs)
        except Exception:
            observe("system_failure", producer=producer, failure=True)
            observe("system_seconds", monotonic() - start, producer)
            raise
        observe(
            "system_seconds",
            monotonic() - start,
            producer,
            connection=kwargs["transaction"],
        )
        resolved("system_failure", producer, connection=kwargs["transaction"])
        return result

    return measured


async def request_metrics(request, call_next):
    path = request.url.path
    start = monotonic()
    response = await call_next(request)
    if path.startswith("/api/v1/messages/") and path.endswith("/send"):
        await asyncio.to_thread(
            observe,
            "send_failure" if response.status_code >= 400 else "send_success",
            failure=response.status_code >= 400,
        )
    elif path == "/api/v1/messages/catch-up" and response.status_code >= 400:
        await asyncio.to_thread(observe, "catchup_failure", failure=True)
    elif path.endswith("/capture") or getattr(request.state, "message_capture", False):
        await asyncio.to_thread(observe, "capture_seconds", monotonic() - start)
        if response.status_code >= 400:
            await asyncio.to_thread(observe, "capture_failure", failure=True)
    elif path.startswith(
        "/api/v1/notification-administration/producers/"
    ) and path.endswith("/test"):
        from .notification_registry import registry

        producer = path.split("/")[-2]
        if producer not in registry.definitions:
            producer = ""
        await asyncio.to_thread(
            observe,
            "test_failure" if response.status_code >= 400 else "test_success",
            producer=producer,
            failure=response.status_code >= 400,
        )
        await asyncio.to_thread(observe, "test_seconds", monotonic() - start, producer)
        if response.status_code == 429:
            await asyncio.to_thread(observe, "test_rate_rejected", producer=producer)
    if response.status_code < 400:
        failure_metric = (
            "send_failure"
            if path.endswith("/send")
            else (
                "catchup_failure"
                if path == "/api/v1/messages/catch-up"
                else (
                    "capture_failure"
                    if path.endswith("/capture")
                    or getattr(request.state, "message_capture", False)
                    else (
                        "test_failure"
                        if path.startswith(
                            "/api/v1/notification-administration/producers/"
                        )
                        and path.endswith("/test")
                        else None
                    )
                )
            )
        )
        if failure_metric:
            await asyncio.to_thread(
                resolved,
                failure_metric,
                producer if failure_metric == "test_failure" else "",
            )
    return response
