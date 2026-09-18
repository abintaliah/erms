"""Bounded cleanup for expired and retained revoked login sessions."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import integer_environment
from .database import database_url


LOCK_KEY = 2_026_091_801


@dataclass
class SessionCleanupResult:
    selected: int = 0
    expired_events: int = 0
    revocation_events_backfilled: int = 0
    removed: int = 0


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _snapshot(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session["id"],
        "client_ip": str(session["client_ip"]) if session.get("client_ip") else None,
        "user_agent": (
            session["user_agent"][:1000] if session.get("user_agent") else None
        ),
        "session_created_at": _timestamp(session.get("date_created")),
        "last_seen_at": _timestamp(session.get("last_seen_at")),
        "expires_at": _timestamp(session.get("expires_at")),
        "absolute_expires_at": _timestamp(session.get("absolute_expires_at")),
        "revoked_at": _timestamp(session.get("revoked_at")),
    }


def _has_revocation_event(connection: Connection, session_id: int) -> bool:
    return connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
              FROM event_history
             WHERE operation = 'SESSION_REVOKED'
               AND (
                    metadata @> jsonb_build_object('session_id', %s)
                    OR metadata -> 'sessions' @> jsonb_build_array(
                        jsonb_build_object('session_id', %s)
                    )
               )
        ) AS found
        """,
        (session_id, session_id),
    ).fetchone()["found"]


def cleanup_sessions(
    connection: Connection,
    *,
    retention_days: int = 90,
    batch_size: int = 500,
    dry_run: bool = False,
) -> SessionCleanupResult:
    result = SessionCleanupResult()
    connection.execute(
        """SELECT set_config('app.actor_type', 'automated_process', true),
                  set_config('app.actor_name', 'Login session cleanup worker', true),
                  set_config('app.event_source', 'scheduled_job', true),
                  set_config('app.change_reason', 'Expired login-session retention period', true)"""
    )
    locked = connection.execute(
        "SELECT pg_try_advisory_xact_lock(%s) AS locked", (LOCK_KEY,)
    ).fetchone()
    if not locked["locked"]:
        return result

    sessions = connection.execute(
        """
        SELECT id, user_id, client_ip, user_agent, date_created, last_seen_at,
               expires_at, absolute_expires_at, revoked_at
          FROM login_sessions
         WHERE (revoked_at IS NOT NULL
                AND revoked_at <= CURRENT_TIMESTAMP - make_interval(days => %s))
            OR (revoked_at IS NULL
                AND LEAST(expires_at, absolute_expires_at)
                    <= CURRENT_TIMESTAMP - make_interval(days => %s))
         ORDER BY COALESCE(revoked_at, LEAST(expires_at, absolute_expires_at)), id
         FOR UPDATE SKIP LOCKED
         LIMIT %s
        """,
        (retention_days, retention_days, batch_size),
    ).fetchall()
    result.selected = len(sessions)
    if dry_run:
        return result

    for session in sessions:
        metadata = _snapshot(session)
        if session["revoked_at"] is None:
            metadata.update({
                "termination_reason": "expired",
                "retention_days": retention_days,
            })
            connection.execute(
                "SELECT append_domain_event('user', %s, 'SESSION_EXPIRED', %s)",
                (session["user_id"], Jsonb(metadata)),
            )
            result.expired_events += 1
        elif not _has_revocation_event(connection, session["id"]):
            metadata.update({
                "revocation_scope": "individual",
                "revocation_reason": "legacy_revocation_audit_backfill",
                "sessions_revoked": 1,
                "retention_days": retention_days,
            })
            connection.execute(
                "SELECT append_domain_event('user', %s, 'SESSION_REVOKED', %s)",
                (session["user_id"], Jsonb(metadata)),
            )
            result.revocation_events_backfilled += 1
        connection.execute("DELETE FROM login_sessions WHERE id = %s", (session["id"],))
        result.removed += 1
    return result


def run_once(
    *, retention_days: int, batch_size: int, dry_run: bool,
) -> SessionCleanupResult:
    with psycopg.connect(database_url(), row_factory=dict_row) as connection:
        result = cleanup_sessions(
            connection,
            retention_days=retention_days,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        if dry_run:
            connection.rollback()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and remove expired or retained revoked ERMS login sessions"
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=integer_environment("AUTH_SESSION_RETENTION_DAYS", 90, minimum=0),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=integer_environment("AUTH_SESSION_CLEANUP_BATCH_SIZE", 500, minimum=1),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=integer_environment(
            "AUTH_SESSION_CLEANUP_INTERVAL_SECONDS", 3600, minimum=1
        ),
    )
    arguments = parser.parse_args()
    if arguments.retention_days < 0:
        parser.error("--retention-days cannot be negative")
    if arguments.batch_size < 1:
        parser.error("--batch-size must be positive")

    while True:
        result = run_once(
            retention_days=arguments.retention_days,
            batch_size=arguments.batch_size,
            dry_run=arguments.dry_run,
        )
        print(
            f"selected={result.selected} expired_events={result.expired_events} "
            f"revocation_events_backfilled={result.revocation_events_backfilled} "
            f"removed={result.removed} dry_run={arguments.dry_run}",
            flush=True,
        )
        if not arguments.watch:
            return
        time.sleep(arguments.interval_seconds)


if __name__ == "__main__":
    main()
