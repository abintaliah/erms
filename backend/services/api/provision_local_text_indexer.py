from __future__ import annotations

import argparse
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from .config import required_environment
from .service_authentication import generate_api_key


def provision(database_url: str, api_url: str, secret_file: Path) -> None:
    target = urlparse(api_url)
    database = urlparse(database_url)
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("automatic provisioning requires a loopback HTTP API URL")
    if database.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("automatic provisioning refuses a non-local database")
    key, identifier, digest = generate_api_key()
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        account = connection.execute(
            "SELECT id,status,account_type FROM users WHERE external_id='local-development-text-indexer' FOR UPDATE"
        ).fetchone()
        if account is None:
            account = connection.execute(
                """INSERT INTO users(name,external_id,account_type)
                   VALUES ('Local Text Indexer','local-development-text-indexer','service')
                   RETURNING id,status,account_type"""
            ).fetchone()
        if account["status"] != "active" or account["account_type"] != "service":
            raise RuntimeError("local text-indexer account exists but is not an active service account")
        role = connection.execute(
            "SELECT id FROM roles WHERE code='text-indexer-service' AND is_system"
        ).fetchone()
        if role is None:
            raise RuntimeError("protected text-indexer service role is missing")
        connection.execute(
            """INSERT INTO user_role_assignments(user_id,role_id)
               SELECT %s,%s WHERE NOT EXISTS (
                 SELECT 1 FROM user_role_assignments WHERE user_id=%s AND role_id=%s
                   AND valid_from<=CURRENT_TIMESTAMP AND (valid_until IS NULL OR valid_until>CURRENT_TIMESTAMP))""",
            (account["id"],role["id"],account["id"],role["id"]),
        )
        connection.execute(
            "UPDATE service_account_credentials SET status='revoked',date_revoked=CURRENT_TIMESTAMP WHERE service_user_id=%s AND status='active'",
            (account["id"],),
        )
        connection.execute(
            """INSERT INTO service_account_credentials(
                   service_user_id,name,credential_identifier,secret_hash,expires_at)
               VALUES (%s,'Local stack text indexer',%s,%s,%s)""",
            (account["id"],identifier,digest,datetime.now(timezone.utc)+timedelta(days=30)),
        )
    secret_file.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    descriptor = os.open(secret_file,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,"w",encoding="ascii") as stream:
        stream.write(key+"\n")
    os.chmod(secret_file,stat.S_IRUSR|stat.S_IWUSR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision loopback development text-indexer credentials")
    parser.add_argument("--api-url",required=True)
    parser.add_argument("--secret-file",type=Path,required=True)
    args = parser.parse_args()
    provision(required_environment("DATABASE_URL"),args.api_url,args.secret_file)


if __name__ == "__main__":
    main()
