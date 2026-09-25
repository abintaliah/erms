from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from .config import integer_environment
from .database import database_url


LOCK_KEY = 843_726_201
EXTRACTION_CONFIG = "tika-4.0.0-ocr-eng-ara-v1"
INDEX_CONFIG = "fts-content-v1"
EXTRACTOR_VERSION = "4.0.0"


def reconcile(connection: Connection, batch_size: int, dry_run: bool) -> dict[str, int]:
    rows = connection.execute(
        """SELECT component.id AS component_id,component.record_id,component.mime_type,
                  content_set.id AS content_set_id,content_set.checksum_algo,content_set.checksum_value
             FROM digital_components component
             JOIN digital_component_content_sets content_set ON content_set.id=component.active_content_set_id
             LEFT JOIN digital_component_search_documents document ON document.digital_component_id=component.id
            WHERE component.content_status='available' AND content_set.status='active'
              AND (document.digital_component_id IS NULL OR document.content_set_id<>content_set.id
                   OR document.extraction_config_version<>%s OR document.index_config_version<>%s)
            ORDER BY component.id LIMIT %s FOR UPDATE OF component SKIP LOCKED""",
        (EXTRACTION_CONFIG, INDEX_CONFIG, batch_size),
    ).fetchall()
    if dry_run:
        return {"drifted": len(rows), "queued": 0}
    queued = 0
    for row in rows:
        connection.execute(
            """INSERT INTO digital_component_search_documents(
                   digital_component_id,record_id,content_set_id,content_checksum_algo,content_checksum_value,
                   status,extraction_config_version,index_config_version)
               VALUES (%s,%s,%s,%s,%s,'pending',%s,%s)
               ON CONFLICT(digital_component_id) DO UPDATE SET record_id=EXCLUDED.record_id,
                   content_set_id=EXCLUDED.content_set_id,content_checksum_algo=EXCLUDED.content_checksum_algo,
                   content_checksum_value=EXCLUDED.content_checksum_value,status='pending',
                   extraction_config_version=EXCLUDED.extraction_config_version,
                   index_config_version=EXCLUDED.index_config_version,date_updated=CURRENT_TIMESTAMP""",
            (row["component_id"],row["record_id"],row["content_set_id"],row["checksum_algo"],
             row["checksum_value"],EXTRACTION_CONFIG,INDEX_CONFIG),
        )
        result = connection.execute(
            """INSERT INTO content_indexing_jobs(
                   digital_component_id,record_id,content_set_id,content_checksum_algo,content_checksum_value,
                   trigger,priority,extraction_config_version,index_config_version,extractor_version,required_capabilities)
               VALUES (%s,%s,%s,%s,%s,'backfill',-10,%s,%s,%s,
                       jsonb_build_object('mime_type',%s::text,'max_input_bytes',52428800))
               ON CONFLICT(digital_component_id,content_set_id,extraction_config_version,index_config_version,extractor_version)
                   WHERE status IN ('queued','leased') DO NOTHING RETURNING id""",
            (row["component_id"],row["record_id"],row["content_set_id"],row["checksum_algo"],
             row["checksum_value"],EXTRACTION_CONFIG,INDEX_CONFIG,EXTRACTOR_VERSION,row["mime_type"]),
        ).fetchone()
        queued += result is not None
    return {"drifted": len(rows), "queued": queued}


def cleanup(
    connection: Connection, batch_size: int, retention_days: int, dry_run: bool,
    credential_retention_days: int = 365,
) -> dict[str, int | bool]:
    leader = connection.execute("SELECT pg_try_advisory_xact_lock(%s) AS acquired", (LOCK_KEY,)).fetchone()["acquired"]
    if not leader:
        return {"leader": False, "staging": 0, "operations": 0, "jobs": 0, "attempts": 0, "credentials": 0}
    counts: dict[str, int | bool] = {"leader": True}
    targets = {
        "staging": """DELETE FROM content_indexing_result_chunks WHERE ctid IN (
            SELECT chunk.ctid FROM content_indexing_result_chunks chunk JOIN content_indexing_jobs job ON job.id=chunk.job_id
            WHERE job.status<>'leased' OR job.lease_generation<>chunk.lease_generation
               OR job.lease_expires_at<CURRENT_TIMESTAMP ORDER BY chunk.date_staged LIMIT %s)""",
        "operations": """DELETE FROM content_indexing_operations WHERE ctid IN (
            SELECT operation.ctid FROM content_indexing_operations operation JOIN content_indexing_jobs job ON job.id=operation.job_id
            WHERE job.completed_at<CURRENT_TIMESTAMP-(%s*interval '1 day') ORDER BY operation.date_created LIMIT %s)""",
        "jobs": """DELETE FROM content_indexing_jobs WHERE id IN (
            SELECT id FROM content_indexing_jobs WHERE status IN ('succeeded','failed','unsupported','cancelled','skipped')
            AND completed_at<CURRENT_TIMESTAMP-(%s*interval '1 day') ORDER BY completed_at LIMIT %s)""",
        "attempts": """DELETE FROM content_indexing_attempts WHERE id IN (
            SELECT id FROM content_indexing_attempts WHERE status<>'processing'
            AND completed_at<CURRENT_TIMESTAMP-(%s*interval '1 day') ORDER BY completed_at LIMIT %s)""",
        "credentials": """DELETE FROM service_account_credentials WHERE id IN (
            SELECT id FROM service_account_credentials
             WHERE (status='revoked' AND date_revoked<CURRENT_TIMESTAMP-(%s*interval '1 day'))
                OR (status='active' AND expires_at<CURRENT_TIMESTAMP-(%s*interval '1 day'))
             ORDER BY coalesce(date_revoked,expires_at),id LIMIT %s)""",
    }
    if dry_run:
        counts.update({name: 0 for name in targets})
        return counts
    counts["staging"] = connection.execute(targets["staging"], (batch_size,)).rowcount
    counts["operations"] = connection.execute(targets["operations"], (retention_days,batch_size)).rowcount
    # Jobs precede attempts safely because attempt.job_id is ON DELETE SET NULL.
    counts["jobs"] = connection.execute(targets["jobs"], (retention_days,batch_size)).rowcount
    counts["attempts"] = connection.execute(targets["attempts"], (retention_days,batch_size)).rowcount
    counts["credentials"] = connection.execute(
        targets["credentials"],
        (credential_retention_days, credential_retention_days, batch_size),
    ).rowcount
    return counts


def run_cleanup_once(
    *, batch_size: int, retention_days: int, credential_retention_days: int,
    dry_run: bool,
) -> dict[str, int | bool]:
    with psycopg.connect(database_url(), row_factory=dict_row) as connection:
        result = cleanup(
            connection, batch_size, retention_days, dry_run,
            credential_retention_days,
        )
        if dry_run:
            connection.rollback()
        return result


def metrics(connection: Connection) -> dict:
    queue = connection.execute("SELECT status,count(*) AS count FROM content_indexing_jobs GROUP BY status").fetchall()
    stale = connection.execute("SELECT count(*) AS count FROM digital_component_search_documents WHERE status='stale'").fetchone()["count"]
    oldest = connection.execute("SELECT extract(epoch FROM CURRENT_TIMESTAMP-min(queued_at))::bigint AS seconds FROM content_indexing_jobs WHERE status='queued'").fetchone()["seconds"]
    attempts = connection.execute(
        """SELECT status,coalesce(error_code,'none') AS error_code,count(*) AS count,
                  round(avg(extract(epoch FROM completed_at-started_at))::numeric,3)::double precision AS average_seconds,
                  coalesce(sum(characters_extracted),0)::bigint AS characters,
                  coalesce(sum(chunks_created),0)::bigint AS chunks,
                  count(*) FILTER (WHERE ocr_used) AS ocr_attempts
             FROM content_indexing_attempts
            GROUP BY status,coalesce(error_code,'none') ORDER BY status,error_code"""
    ).fetchall()
    content = connection.execute(
        """SELECT count(*) AS content_sets,coalesce(sum(content_set.size_in_bytes),0)::bigint AS bytes
             FROM content_indexing_jobs job
             JOIN digital_component_content_sets content_set ON content_set.id=job.content_set_id"""
    ).fetchone()
    workers = connection.execute(
        """SELECT count(*) FILTER (WHERE active_until>=CURRENT_TIMESTAMP) AS active,
                  count(*) FILTER (WHERE active_until<CURRENT_TIMESTAMP) AS stale
             FROM text_indexing_workers"""
    ).fetchone()
    recovery = connection.execute(
        """SELECT count(*) FILTER (WHERE status='leased' AND lease_expires_at<CURRENT_TIMESTAMP) AS expired_leases,
                  (SELECT count(*) FROM content_indexing_attempts WHERE status='lease_lost') AS lease_lost_attempts
             FROM content_indexing_jobs"""
    ).fetchone()
    staging = connection.execute("SELECT count(*) AS chunks FROM content_indexing_result_chunks").fetchone()["chunks"]
    return {
        "queue": {row["status"]: row["count"] for row in queue},
        "stale_documents": stale, "oldest_queued_seconds": oldest,
        "outcomes": [dict(row) for row in attempts],
        "input": {"content_sets": content["content_sets"], "bytes": content["bytes"]},
        "workers": dict(workers), "recovery": dict(recovery),
        "staged_chunks": staging,
    }


def drifted_document_count(connection: Connection) -> int:
    return connection.execute(
        """SELECT count(*) AS count
             FROM digital_components component
             JOIN digital_component_content_sets content_set
               ON content_set.id=component.active_content_set_id
             LEFT JOIN digital_component_search_documents document
               ON document.digital_component_id=component.id
            WHERE component.content_status='available' AND content_set.status='active'
              AND (document.digital_component_id IS NULL
                   OR document.content_set_id<>content_set.id
                   OR document.extraction_config_version<>%s
                   OR document.index_config_version<>%s)""",
        (EXTRACTION_CONFIG, INDEX_CONFIG),
    ).fetchone()["count"]


def readiness(connection: Connection) -> dict:
    state = metrics(connection)
    drift = drifted_document_count(connection)
    blocking_jobs = sum(state["queue"].get(name, 0) for name in ("queued", "leased"))
    failed = state["queue"].get("failed", 0)
    ready = drift == 0 and blocking_jobs == 0 and state["stale_documents"] == 0 and failed == 0
    return {
        "ready_for_search": ready,
        "drifted_documents": drift,
        "blocking_jobs": blocking_jobs,
        "failed_jobs": failed,
        "stale_documents": state["stale_documents"],
        "active_workers": state["workers"]["active"],
        "metrics": state,
    }


def quality_gate(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    summary = result["summary"]
    thresholds = {"english_recall": 0.90, "arabic_recall": 0.75, "marker_recall": 0.90}
    checks = {name: float(summary[name]) >= threshold for name, threshold in thresholds.items()}
    return {
        "passed": all(checks.values()), "checks": checks,
        "thresholds": thresholds,
        "observed": {name: summary[name] for name in thresholds},
        "source": str(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="API-owned text-indexing maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("reconcile", "cleanup"):
        command = commands.add_parser(name)
        command.add_argument(
            "--batch-size", type=int,
            default=integer_environment("CONTENT_INDEXING_CLEANUP_BATCH_SIZE", 500, minimum=1),
        )
        command.add_argument("--dry-run", action="store_true")
    commands.choices["cleanup"].add_argument(
        "--retention-days", type=int,
        default=integer_environment("CONTENT_INDEXING_HISTORY_RETENTION_DAYS", 365, minimum=0),
    )
    commands.choices["cleanup"].add_argument(
        "--credential-retention-days", type=int,
        default=integer_environment(
            "TEXT_INDEXER_CREDENTIAL_HISTORY_RETENTION_DAYS", 365, minimum=0,
        ),
    )
    commands.choices["cleanup"].add_argument("--watch", action="store_true")
    commands.choices["cleanup"].add_argument(
        "--interval-seconds", type=int,
        default=integer_environment(
            "CONTENT_INDEXING_CLEANUP_INTERVAL_SECONDS", 3600, minimum=1,
        ),
    )
    commands.add_parser("metrics")
    commands.add_parser("readiness")
    quality = commands.add_parser("quality-gate")
    quality.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.command == "quality-gate":
        result = quality_gate(args.report)
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(0 if result["passed"] else 1)
    if args.command == "cleanup":
        if args.batch_size < 1:
            parser.error("--batch-size must be positive")
        if args.retention_days < 0 or args.credential_retention_days < 0:
            parser.error("retention days cannot be negative")
        if args.interval_seconds < 1:
            parser.error("--interval-seconds must be positive")
        while True:
            result = run_cleanup_once(
                batch_size=args.batch_size,
                retention_days=args.retention_days,
                credential_retention_days=args.credential_retention_days,
                dry_run=args.dry_run,
            )
            print(json.dumps(result, sort_keys=True), flush=True)
            if not args.watch:
                return
            time.sleep(args.interval_seconds)

    with psycopg.connect(database_url(), row_factory=dict_row) as connection:
        if args.command == "reconcile": result = reconcile(connection,args.batch_size,args.dry_run)
        elif args.command == "metrics": result = metrics(connection)
        else: result = readiness(connection)
    print(json.dumps(result,sort_keys=True))
    if args.command == "readiness" and not result["ready_for_search"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
