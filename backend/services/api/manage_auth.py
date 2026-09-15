from __future__ import annotations

import argparse
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from .authentication import SYSTEM_ADMIN_ROLE, hash_password
from .config import required_environment


def set_temporary_password(connection, email: str, *, make_admin: bool, org_unit_code: str | None) -> str:
    user = connection.execute(
        "SELECT id, account_type FROM users WHERE lower(email)=lower(%s)", (email,)
    ).fetchone()
    if not user:
        raise RuntimeError(f"no user exists with email {email}")
    if user["account_type"] != "human":
        raise RuntimeError("interactive passwords can only be issued to human users")
    password = secrets.token_urlsafe(15)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    connection.execute(
        """
        INSERT INTO user_credentials (user_id,password_hash,must_change_password,temporary_expires_at)
        VALUES (%s,%s,true,%s)
        ON CONFLICT (user_id) DO UPDATE SET password_hash=EXCLUDED.password_hash,
          must_change_password=true, temporary_expires_at=EXCLUDED.temporary_expires_at,
          failed_attempt_count=0, locked_until=NULL, date_updated=CURRENT_TIMESTAMP
        """, (user["id"], hash_password(password), expires_at)
    )
    connection.execute(
        "UPDATE login_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=%s AND revoked_at IS NULL",
        (user["id"],),
    )
    if make_admin:
        if not org_unit_code:
            raise RuntimeError("--org-unit-code is required when assigning system administrator")
        org = connection.execute("SELECT id FROM org_units WHERE lower(code)=lower(%s)", (org_unit_code,)).fetchone()
        if not org:
            raise RuntimeError(f"organization unit {org_unit_code} does not exist")
        role = connection.execute("SELECT id FROM roles WHERE lower(code)=lower(%s)", (SYSTEM_ADMIN_ROLE,)).fetchone()
        if not role:
            role = connection.execute(
                "INSERT INTO roles (org_unit_id,code,name,description) VALUES (%s,%s,'System Administrator','Reserved platform administration role') RETURNING id",
                (org["id"], SYSTEM_ADMIN_ROLE),
            ).fetchone()
        connection.execute(
            """INSERT INTO user_role_assignments (user_id,role_id)
               SELECT %s,%s WHERE NOT EXISTS (
                 SELECT 1 FROM user_role_assignments WHERE user_id=%s AND role_id=%s AND valid_until IS NULL
               )""", (user["id"], role["id"], user["id"], role["id"]),
        )
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="ERMS local-authentication recovery utility")
    parser.add_argument("email")
    parser.add_argument("--make-system-administrator", action="store_true")
    parser.add_argument("--org-unit-code")
    args = parser.parse_args()
    with psycopg.connect(required_environment("DATABASE_URL"), row_factory=dict_row) as connection:
        password = set_temporary_password(
            connection, args.email,
            make_admin=args.make_system_administrator,
            org_unit_code=args.org_unit_code,
        )
    print("Temporary password (shown once):")
    print(password)
    print("It expires in 24 hours and must be changed at first login.")


if __name__ == "__main__":
    main()
