"""Content-free API endpoint identity and fixed gateway heartbeat lifecycle."""

import ipaddress
import logging
import os
import socket

import psutil

logger = logging.getLogger(__name__)

# A stale report is not evidence that the PostgreSQL listener is disconnected.
HEALTH_STATUS_SQL = """CASE
 WHEN observed_at < CURRENT_TIMESTAMP - interval '45 seconds' THEN 'overdue'
 WHEN NOT listener_connected THEN 'disconnected'
 ELSE 'connected' END"""
CURRENT_REPORT_SQL = "observed_at > CURRENT_TIMESTAMP - interval '24 hours'"


def endpoint_identity():
    """Use a concrete bind, or enumerate the owning process's live interfaces.

    Do not guess a preferred LAN/VPN/container address. Multiple candidates are
    reported together; the UI explicitly identifies their ambiguity. Collection
    happens on each heartbeat so interface changes need no process restart.
    """
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise RuntimeError("API_PORT must be between 1 and 65535")
    try:
        bind = ipaddress.ip_address(host)
    except ValueError:
        bind = None
    if bind is not None and not bind.is_unspecified:
        return [str(bind)], port
    addresses = set()
    try:
        if bind is None:
            candidates = [r[4][0] for r in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
        else:
            stats = psutil.net_if_stats()
            candidates = [
                addr.address.split("%", 1)[0]
                for name, entries in psutil.net_if_addrs().items()
                if name in stats and stats[name].isup
                for addr in entries
                if addr.family in (socket.AF_INET, socket.AF_INET6)
                and (bind.version == 6 or addr.family == socket.AF_INET)
            ]
        for candidate in candidates:
            address = ipaddress.ip_address(candidate)
            if not address.is_unspecified and not address.is_multicast:
                addresses.add(address)
    except (OSError, ValueError, psutil.Error):
        # Failure to discover identity must not stop health reporting.
        logger.warning("messaging_gateway_address_discovery_failed")
    return [str(a) for a in sorted(addresses, key=lambda a: (a.version, int(a)))], port


def retire_expired(connection):
    """Predicate is rechecked under row locks after concurrent heartbeat writes."""
    return connection.execute(
        "DELETE FROM messaging_gateway_health "
        "WHERE observed_at <= CURRENT_TIMESTAMP - interval '24 hours'"
    ).rowcount
