#!/usr/bin/env python3
"""Read-only operational checks for authorization continuity and security signals."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from backend.services.api.authorization_admin import CUSTODY_PRIVILEGE_CODES


def _connection(url: str):
    return psycopg.connect(url, row_factory=dict_row)


def summary(connection, hours: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = list(connection.execute(
        """SELECT operation,count(*)::int AS count,max(occurred_at) AS last_seen_at
           FROM event_history WHERE occurred_at>=%s
             AND operation IN ('AUTHORIZATION_DENIED','AUTHENTICATION_FAILED','ACCOUNT_LOCKED',
               'INFORMATION_GOVERNANCE_BYPASS_USED','ACCESS_EXPLANATION_VIEWED',
               'SECURITY_LEVEL_CHANGED','SECURITY_LEVEL_UPGRADED','SECURITY_LEVEL_DOWNGRADED',
               'ACL_REPLACED','PROFILE_PRIVILEGES_REPLACED','PROFILE_ASSIGNED')
           GROUP BY operation ORDER BY count(*) DESC,operation""", (since,),
    ).fetchall())
    return {"window_hours": hours, "events": rows,
            "total": sum(row["count"] for row in rows)}


def reconcile(connection) -> dict:
    admin_count = connection.execute(
        """SELECT count(DISTINCT account.id)::int AS value FROM users account
           JOIN user_role_assignments assignment ON assignment.user_id=account.id
           JOIN roles role ON role.id=assignment.role_id
           JOIN profile_privileges membership ON membership.profile_id=role.profile_id
           JOIN privileges privilege ON privilege.id=membership.privilege_id
           WHERE account.status='active' AND role_effectively_active(role.id)
             AND assignment.valid_from<=CURRENT_TIMESTAMP
             AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
             AND privilege.code='authorization.administer'"""
    ).fetchone()["value"]
    highest = connection.execute("SELECT max(level_number) AS value FROM security_levels").fetchone()["value"]
    custodian_count = connection.execute(
        """SELECT count(DISTINCT account.id)::int AS value FROM users account
           JOIN user_role_assignments assignment ON assignment.user_id=account.id
           JOIN roles role ON role.id=assignment.role_id
           JOIN security_levels level ON level.id=role.security_level_id
           WHERE account.status='active' AND role.is_information_governance
             AND level.level_number>=%s AND role_effectively_active(role.id)
             AND assignment.valid_from<=CURRENT_TIMESTAMP
             AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
             AND (SELECT count(DISTINCT privilege.code) FROM profile_privileges membership
                  JOIN privileges privilege ON privilege.id=membership.privilege_id
                  WHERE membership.profile_id=role.profile_id AND privilege.code=ANY(%s))=%s""",
        (highest, list(CUSTODY_PRIVILEGE_CODES), len(CUSTODY_PRIVILEGE_CODES)),
    ).fetchone()["value"]
    findings = []
    if admin_count == 0: findings.append({"code": "zero_authorization_administrators", "severity": "critical"})
    elif admin_count == 1: findings.append({"code": "single_authorization_administrator", "severity": "advisory"})
    if custodian_count == 0: findings.append({"code": "zero_universal_governance_custodians", "severity": "critical"})
    elif custodian_count == 1: findings.append({"code": "single_universal_governance_custodian", "severity": "advisory"})
    return {"authorization_administrator_count": admin_count,
            "universal_governance_custodian_count": custodian_count, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("summary", "reconcile"))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--fail-on-critical", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    with _connection(args.database_url) as connection:
        result = summary(connection, args.hours) if args.command == "summary" else reconcile(connection)
    print(json.dumps(result, default=str, indent=2))
    return 2 if args.fail_on_critical and any(
        item.get("severity") == "critical" for item in result.get("findings", [])
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
