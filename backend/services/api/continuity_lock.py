"""Coordination for mutations that can reduce authorization continuity."""

from psycopg import Connection


CONTINUITY_LOCK_NAMESPACE = 1163021645
CONTINUITY_LOCK_KEY = 1


def acquire_continuity_lock(connection: Connection) -> None:
    """Serialize only participating continuity mutations for this transaction."""
    connection.execute(
        "SELECT pg_advisory_xact_lock(%s,%s)",
        (CONTINUITY_LOCK_NAMESPACE, CONTINUITY_LOCK_KEY),
    )


def acquire_continuity_shared_lock(connection: Connection) -> None:
    """Allow concurrent protected-resource creation, but exclude continuity loss."""
    connection.execute(
        "SELECT pg_advisory_xact_lock_shared(%s,%s)",
        (CONTINUITY_LOCK_NAMESPACE, CONTINUITY_LOCK_KEY),
    )
