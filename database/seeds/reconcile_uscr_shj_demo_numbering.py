#!/usr/bin/env python3
"""Renumber the version-1 USCR-SHJ Arabic demo dataset to its governed format."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import uuid

import psycopg
from psycopg.rows import dict_row

from database.seeds.seed_uscr_shj_arabic_demo import (
    AGGREGATION_COUNT,
    DEFAULT_CORPUS,
    EXPECTED_RECORD_COUNT,
    LEGACY_AGGREGATION_PREFIX,
    LEGACY_RECORD_PREFIX,
    NUMBERING_YEAR,
    SEED_NAME,
    build_plan,
    load_corpus,
    verify_existing,
)


CORRECTION_NAME = "004_reconcile_uscr_shj_demo_numbering"


def seeded_rows(connection: psycopg.Connection, entity_type: str, table: str) -> list[dict]:
    return connection.execute(
        f"""SELECT resource.id, resource.{('aggregation_number' if table == 'aggregations' else 'record_number')} AS current_number,
                   original.after_state->>%s AS original_number
              FROM {table} resource
              JOIN LATERAL (
                  SELECT event.after_state
                    FROM event_history event
                   WHERE event.entity_type=%s AND event.entity_id=resource.id
                     AND event.operation='CREATE' AND event.metadata->>'seed'=%s
                   ORDER BY event.id LIMIT 1
              ) original ON true
             ORDER BY resource.id""",
        ("aggregation_number" if table == "aggregations" else "record_number", entity_type, SEED_NAME),
    ).fetchall()


def reconcile(database_url: str, corpus_root: Path) -> bool:
    corpus, manifest_checksum = load_corpus(corpus_root)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            aggregations, records = build_plan(connection, corpus)
            aggregation_rows = seeded_rows(connection, "aggregation", "aggregations")
            record_rows = seeded_rows(connection, "record", "records")
            if len(aggregation_rows) != AGGREGATION_COUNT or len(record_rows) != EXPECTED_RECORD_COUNT:
                raise RuntimeError(
                    f"expected {AGGREGATION_COUNT} seeded aggregations and {EXPECTED_RECORD_COUNT} records; "
                    f"found {len(aggregation_rows)} and {len(record_rows)}"
                )

            aggregation_by_original = {row["original_number"]: row for row in aggregation_rows}
            record_by_original = {row["original_number"]: row for row in record_rows}
            aggregation_updates: list[tuple[str, int]] = []
            record_updates: list[tuple[str, int]] = []
            all_current = True
            all_legacy = True

            for plan in aggregations:
                legacy = f"{LEGACY_AGGREGATION_PREFIX}{plan.sequence:04d}"
                row = aggregation_by_original.get(legacy)
                if row is None:
                    raise RuntimeError(f"missing original seeded aggregation identity {legacy}")
                all_current = all_current and row["current_number"] == plan.number
                all_legacy = all_legacy and row["current_number"] == legacy
                aggregation_updates.append((plan.number, row["id"]))

            for plan in records:
                legacy = f"{LEGACY_RECORD_PREFIX}{plan.sequence:05d}"
                row = record_by_original.get(legacy)
                if row is None:
                    raise RuntimeError(f"missing original seeded record identity {legacy}")
                all_current = all_current and row["current_number"] == plan.number
                all_legacy = all_legacy and row["current_number"] == legacy
                record_updates.append((plan.number, row["id"]))

            if all_current:
                if not verify_existing(connection, aggregations, records, manifest_checksum):
                    raise RuntimeError("renumbered seed verification failed")
                return False
            if not all_legacy:
                raise RuntimeError("seeded numbering is partially changed or conflicts with the supported legacy dataset")

            aggregation_ids = [row["id"] for row in aggregation_rows]
            record_ids = [row["id"] for row in record_rows]
            aggregation_targets = [number for number, _ in aggregation_updates]
            record_targets = [number for number, _ in record_updates]
            if connection.execute(
                "SELECT count(*) FROM aggregations WHERE aggregation_number=ANY(%s) AND NOT (id=ANY(%s))",
                (aggregation_targets, aggregation_ids),
            ).fetchone()["count"]:
                raise RuntimeError("one or more target aggregation numbers already belong to other rows")
            if connection.execute(
                "SELECT count(*) FROM records WHERE record_number=ANY(%s) AND NOT (id=ANY(%s))",
                (record_targets, record_ids),
            ).fetchone()["count"]:
                raise RuntimeError("one or more target record numbers already belong to other rows")

            correlation_id = str(uuid.uuid4())
            metadata = {
                "seed": CORRECTION_NAME,
                "source_seed": SEED_NAME,
                "numbering_year": NUMBERING_YEAR,
                "aggregation_count": AGGREGATION_COUNT,
                "record_count": EXPECTED_RECORD_COUNT,
                "numbering_policy": {
                    "aggregation": "<terminal-classification-code>/<year>/<classification-local-serial>",
                    "record": "<parent-aggregation-number>.<aggregation-local-serial>",
                },
            }
            for setting, value in (
                ("app.actor_type", "automated_process"),
                ("app.actor_name", "USCR-SHJ Arabic Demo Numbering Reconciler"),
                ("app.event_source", "seeding"),
                ("app.change_reason", "Apply the approved classification-local numbering convention to USCR-SHJ demo data"),
                ("app.correlation_id", correlation_id),
                ("app.event_metadata", json.dumps(metadata, ensure_ascii=False)),
            ):
                connection.execute("SELECT set_config(%s,%s,true)", (setting, value))

            with connection.cursor() as cursor:
                cursor.executemany(
                    "UPDATE aggregations SET aggregation_number=%s WHERE id=%s",
                    aggregation_updates,
                )
                cursor.executemany(
                    "UPDATE records SET record_number=%s WHERE id=%s",
                    record_updates,
                )
            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            if not verify_existing(connection, aggregations, records, manifest_checksum):
                raise RuntimeError("post-reconciliation seed verification failed")
            correction_events = connection.execute(
                """SELECT count(*) AS events, count(DISTINCT correlation_id) AS correlations,
                          bool_and(source='seeding') AS sources_valid,
                          bool_and(actor_type='automated_process') AS actors_valid
                     FROM event_history WHERE metadata->>'seed'=%s""",
                (CORRECTION_NAME,),
            ).fetchone()
            if correction_events != {
                "events": AGGREGATION_COUNT + EXPECTED_RECORD_COUNT,
                "correlations": 1,
                "sources_valid": True,
                "actors_valid": True,
            }:
                raise RuntimeError(f"numbering audit verification failed: {correction_events}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    changed = reconcile(args.database_url, args.corpus.resolve())
    print("Reconciled USCR-SHJ demo numbering." if changed else "USCR-SHJ demo numbering already matches; no changes made.")


if __name__ == "__main__":
    main()
