#!/usr/bin/env python3
"""Create deterministic Arabic USCR-SHJ demo records with stored sample content."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import uuid

import psycopg
from psycopg.rows import dict_row


SEED_NAME = "004_seed_uscr_shj_arabic_demo"
SEED_VERSION = 2
RANDOM_SEED = 20260924
NUMBERING_YEAR = 2026
AGGREGATION_COUNT = 400
LEGACY_AGGREGATION_PREFIX = "USCR-DEMO-AGG-"
LEGACY_RECORD_PREFIX = "USCR-DEMO-REC-"
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = PROJECT_DIR / "examples/samples/docs"
FORMATS = ("docx", "eml", "html", "jpeg", "md", "msg", "pdf", "png", "pptx", "txt", "xlsx", "xml")
EXPECTED_RECORD_COUNT = 1600
EXPECTED_COMPONENT_COUNT = 3199
ARABIC_RECORD_TYPES = (
    "الخطة المعتمدة وإجراءات التنفيذ",
    "المراسلات والقرارات الإدارية",
    "تقرير المتابعة والنتائج",
    "محضر المراجعة والتوصيات",
    "سجل الأدلة والإجراءات التصحيحية",
)
ENGLISH_RECORD_TYPES = (
    "Approved plan and implementation actions",
    "Correspondence and administrative decisions",
    "Monitoring report and outcomes",
    "Review minutes and recommendations",
    "Evidence register and corrective actions",
)
MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "eml": "message/rfc822",
    "html": "text/html",
    "jpeg": "image/jpeg",
    "md": "text/markdown",
    "msg": "application/vnd.ms-outlook",
    "pdf": "application/pdf",
    "png": "image/png",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xml": "application/xml",
}


@dataclass(frozen=True)
class CorpusFile:
    identifier: int
    format: str
    relative_path: str
    topic: str
    size: int
    checksum: str


@dataclass(frozen=True)
class AggregationPlan:
    sequence: int
    number: str
    title: str
    description: str
    classification_id: int
    classification_code: str
    classification_title: str
    classification_description: str
    owner_id: int
    is_vital: bool
    created: datetime
    topic: str


@dataclass(frozen=True)
class RecordPlan:
    sequence: int
    aggregation_sequence: int
    number: str
    title: str
    description: str
    is_vital: bool
    created: datetime
    topic: str
    component_files: tuple[CorpusFile, ...]


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_corpus(corpus_root: Path) -> tuple[list[CorpusFile], str]:
    manifest_path = corpus_root / "manifest.csv"
    if not manifest_path.is_file():
        raise ValueError(f"sample manifest does not exist: {manifest_path}")
    entries: list[CorpusFile] = []
    with manifest_path.open("r", encoding="utf-8", newline="") as manifest:
        for row in csv.DictReader(manifest):
            if row["format"] not in FORMATS:
                continue
            entry = CorpusFile(
                identifier=int(row["id"]),
                format=row["format"],
                relative_path=row["path"],
                topic=row["topic"],
                size=int(row["size_bytes"]),
                checksum=row["sha256"],
            )
            source_path = corpus_root / entry.relative_path
            if not source_path.is_file():
                raise ValueError(f"manifest file is missing: {source_path}")
            if source_path.stat().st_size != entry.size:
                raise ValueError(f"manifest size mismatch: {source_path}")
            if sha256_file(source_path) != entry.checksum:
                raise ValueError(f"manifest checksum mismatch: {source_path}")
            entries.append(entry)
    if len(entries) != 1200:
        raise ValueError(f"expected 1200 corpus files, found {len(entries)}")
    return entries, sha256_file(manifest_path)


def classification_topic(code: str, english: str) -> str:
    value = english.lower()
    keyword_topics = (
        ("information-technology", ("information technology", "computer", "electronic", "system", "software", "network", "database", "cyber", "technical support")),
        ("records-management", ("record", "document", "archive", "filing", "correspondence", "mail")),
        ("project-management", ("project", "programme", "program ", "initiative", "implementation plan")),
        ("procurement", ("procurement", "purchase", "supplier", "tender", "contract", "bid", "warehouse")),
        ("asset-management", ("asset", "property", "building", "vehicle", "equipment", "inventory", "maintenance", "facility")),
        ("finance", ("financial", "finance", "budget", "account", "payment", "revenue", "expense", "cash", "audit")),
        ("human-resources", ("employee", "staff", "human resource", "recruit", "training", "leave", "career", "personnel", "job", "position")),
    )
    for topic, keywords in keyword_topics:
        if any(keyword in value for keyword in keywords):
            return topic
    if code.startswith("2"):
        return "human-resources"
    if code.startswith("3"):
        return "finance"
    if code.startswith("4"):
        return "asset-management"
    return "general-administration"


def build_plan(connection: psycopg.Connection, corpus: list[CorpusFile]) -> tuple[list[AggregationPlan], list[RecordPlan]]:
    classifications = connection.execute(
        """SELECT classification.id, classification.code, classification.title,
                  classification.description
             FROM classifications classification
             JOIN classification_schemes scheme
               ON scheme.id = classification.classification_scheme_id
            WHERE scheme.code = 'USCR-SHJ'
              AND classification.is_terminal
              AND classification.date_deactivated IS NULL
            ORDER BY classification.code COLLATE \"C\", classification.id"""
    ).fetchall()
    if len(classifications) != 254:
        raise RuntimeError(f"USCR-SHJ must have 254 active terminal classifications; found {len(classifications)}")
    owners = connection.execute(
        """SELECT unit.id, unit.code
             FROM org_units unit
             JOIN roles role ON role.org_unit_id = unit.id
            WHERE unit.status = 'active' AND role.status = 'active'
              AND lower(unit.code) <> 'system'
            GROUP BY unit.id, unit.code
            ORDER BY unit.code COLLATE \"C\", unit.id"""
    ).fetchall()
    if not owners:
        raise RuntimeError("at least one active non-system organizational unit with an active role is required")

    corpus_by_topic_format: dict[tuple[str, str], list[CorpusFile]] = {}
    for entry in corpus:
        corpus_by_topic_format.setdefault((entry.topic, entry.format), []).append(entry)
    for entries in corpus_by_topic_format.values():
        entries.sort(key=lambda item: item.identifier)

    aggregations: list[AggregationPlan] = []
    records: list[RecordPlan] = []
    record_sequence = 0
    component_sequence = 0
    classification_serials: dict[int, int] = {}
    dubai = timezone(timedelta(hours=4))
    for aggregation_sequence in range(1, AGGREGATION_COUNT + 1):
        classification = classifications[(aggregation_sequence - 1) % len(classifications)]
        year = 2022 + ((aggregation_sequence - 1) % 4)
        series = f"{aggregation_sequence:04d}"
        topic = classification_topic(classification["code"], classification["description"] or "")
        classification_serials[classification["id"]] = classification_serials.get(classification["id"], 0) + 1
        aggregation_number = (
            f"{classification['code']}/{NUMBERING_YEAR}/"
            f"{classification_serials[classification['id']]}"
        )
        aggregation = AggregationPlan(
            sequence=aggregation_sequence,
            number=aggregation_number,
            title=f"ملف {classification['title']} — دورة {year} — سلسلة {series}",
            description=f"File for {classification['description']} — operational cycle {year} — series {series}.",
            classification_id=classification["id"],
            classification_code=classification["code"],
            classification_title=classification["title"],
            classification_description=classification["description"],
            owner_id=owners[(aggregation_sequence - 1) % len(owners)]["id"],
            is_vital=(aggregation_sequence - 1) % 10 == 0,
            created=datetime(year, 1 + aggregation_sequence % 12, 1 + aggregation_sequence % 24, 9, aggregation_sequence % 60, tzinfo=dubai),
            topic=topic,
        )
        aggregations.append(aggregation)
        record_count = 3 + aggregation_sequence % 3
        for local_sequence in range(1, record_count + 1):
            record_sequence += 1
            type_index = (record_sequence - 1) % len(ARABIC_RECORD_TYPES)
            record_number = f"{aggregation_number}.{local_sequence}"
            component_count = 1 + (record_sequence - 1) % 3
            selected: list[CorpusFile] = []
            for component_index in range(component_count):
                target_format = FORMATS[component_sequence % len(FORMATS)]
                candidates = corpus_by_topic_format[(topic, target_format)]
                selected.append(candidates[(record_sequence * 17 + component_index * 7 + RANDOM_SEED) % len(candidates)])
                component_sequence += 1
            records.append(
                RecordPlan(
                    sequence=record_sequence,
                    aggregation_sequence=aggregation_sequence,
                    number=record_number,
                    title=f"{ARABIC_RECORD_TYPES[type_index]} — {classification['title']} — {local_sequence:02d}",
                    description=(
                        f"{ENGLISH_RECORD_TYPES[type_index]} for {classification['description']}; "
                        f"record {local_sequence:02d} in operational cycle {year}."
                    ),
                    is_vital=(record_sequence - 1) % 10 == 0,
                    created=aggregation.created + timedelta(days=local_sequence, minutes=record_sequence % 47),
                    topic=topic,
                    component_files=tuple(selected),
                )
            )
    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(f"internal plan error: expected {EXPECTED_RECORD_COUNT} records, found {len(records)}")
    if sum(len(record.component_files) for record in records) != EXPECTED_COMPONENT_COUNT:
        raise RuntimeError("internal plan error: component count mismatch")
    return aggregations, records


def verify_existing(
    connection: psycopg.Connection,
    aggregations: list[AggregationPlan],
    records: list[RecordPlan],
    manifest_checksum: str,
) -> bool:
    counts = connection.execute(
        """WITH seeded_aggregations AS (
                 SELECT DISTINCT entity_id FROM event_history
                  WHERE entity_type='aggregation' AND operation='CREATE' AND metadata->>'seed'=%s
             ), seeded_records AS (
                 SELECT DISTINCT entity_id FROM event_history
                  WHERE entity_type='record' AND operation='CREATE' AND metadata->>'seed'=%s
             )
             SELECT
             (SELECT count(*) FROM aggregations WHERE id IN (SELECT entity_id FROM seeded_aggregations)) AS aggregations,
             (SELECT count(*) FROM records WHERE id IN (SELECT entity_id FROM seeded_records)) AS records,
             (SELECT count(*) FROM digital_components component
               WHERE component.record_id IN (SELECT entity_id FROM seeded_records)) AS components,
             (SELECT count(*) FROM event_history WHERE metadata->>'seed'=%s) AS events""",
        (SEED_NAME, SEED_NAME, SEED_NAME),
    ).fetchone()
    values = [counts[key] for key in ("aggregations", "records", "components", "events")]
    if values == [0, 0, 0, 0]:
        return False
    expected_counts = [AGGREGATION_COUNT, EXPECTED_RECORD_COUNT, EXPECTED_COMPONENT_COUNT]
    if values[:3] != expected_counts or values[3] == 0:
        raise RuntimeError(f"partial or conflicting {SEED_NAME} data exists: {values}")

    expected_aggregations = {
        item.number: (item.title, item.description, item.classification_id, item.owner_id, item.is_vital, item.topic)
        for item in aggregations
    }
    actual_aggregations = connection.execute(
        """SELECT aggregation_number, title, description, classification_id,
                  owning_org_unit_id, is_vital
             FROM aggregations
            WHERE id IN (
                SELECT DISTINCT entity_id FROM event_history
                 WHERE entity_type='aggregation' AND operation='CREATE' AND metadata->>'seed'=%s
            )""",
        (SEED_NAME,),
    ).fetchall()
    for row in actual_aggregations:
        expected = expected_aggregations.get(row["aggregation_number"])
        if expected is None or tuple(row[key] for key in ("title", "description", "classification_id", "owning_org_unit_id", "is_vital")) != expected[:5]:
            raise RuntimeError(f"existing seeded aggregation differs: {row['aggregation_number']}")

    expected_records = {item.number: item for item in records}
    actual_records = connection.execute(
        """SELECT record.record_number, record.title, record.description, record.is_vital,
                  aggregation.aggregation_number
             FROM records record
             JOIN aggregations aggregation ON aggregation.id=record.aggregation_id
            WHERE record.id IN (
                SELECT DISTINCT entity_id FROM event_history
                 WHERE entity_type='record' AND operation='CREATE' AND metadata->>'seed'=%s
            )""",
        (SEED_NAME,),
    ).fetchall()
    for row in actual_records:
        expected = expected_records.get(row["record_number"])
        expected_parent = aggregations[expected.aggregation_sequence - 1].number if expected else None
        if expected is None or (row["title"], row["description"], row["is_vital"], row["aggregation_number"]) != (
            expected.title, expected.description, expected.is_vital, expected_parent
        ):
            raise RuntimeError(f"existing seeded record differs: {row['record_number']}")

    actual_components = connection.execute(
        """SELECT record.record_number, component.component_order, component.file_name,
                  component.size_in_bytes, component.checksum_value, component.content_status,
                  content_set.status AS set_status, content_set.segment_count,
                  blob.segment_size, blob.segment_checksum_value
             FROM digital_components component
             JOIN records record ON record.id=component.record_id
             JOIN digital_component_content_sets content_set ON content_set.id=component.active_content_set_id
             JOIN digital_component_blobs blob ON blob.content_set_id=content_set.id AND blob.segment_no=0
            WHERE record.id IN (
                SELECT DISTINCT entity_id FROM event_history
                 WHERE entity_type='record' AND operation='CREATE' AND metadata->>'seed'=%s
            )
            ORDER BY record.record_number, component.component_order""",
        (SEED_NAME,),
    ).fetchall()
    expected_component_rows = {}
    for record in records:
        for order, entry in enumerate(record.component_files, 1):
            expected_component_rows[(record.number, order)] = (
                Path(entry.relative_path).name, entry.size, entry.checksum
            )
    actual_component_rows = {
        (row["record_number"], row["component_order"]):
        (row["file_name"], row["size_in_bytes"], row["checksum_value"])
        for row in actual_components
    }
    if actual_component_rows != expected_component_rows:
        raise RuntimeError("existing seeded digital-component plan differs")
    if any(
        row["content_status"] != "available" or row["set_status"] != "active"
        or row["segment_count"] != 1 or row["segment_size"] != row["size_in_bytes"]
        or row["segment_checksum_value"] != row["checksum_value"]
        for row in actual_components
    ):
        raise RuntimeError("existing seeded digital-component storage is incomplete")

    audit = connection.execute(
        """SELECT count(*) AS events, count(DISTINCT correlation_id) AS correlations,
                  bool_and(source='seeding') AS sources_valid,
                  bool_and(actor_type='automated_process') AS actors_valid,
                  bool_and(metadata->>'manifest_sha256'=%s) AS manifest_valid
             FROM event_history WHERE metadata->>'seed'=%s""",
        (manifest_checksum, SEED_NAME),
    ).fetchone()
    if audit["correlations"] != 1 or not audit["sources_valid"] or not audit["actors_valid"] or not audit["manifest_valid"]:
        raise RuntimeError("existing seeded audit provenance is incomplete")
    return True


def seed(database_url: str, corpus_root: Path) -> bool:
    corpus, manifest_checksum = load_corpus(corpus_root)
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            aggregations, records = build_plan(connection, corpus)
            if verify_existing(connection, aggregations, records, manifest_checksum):
                return False

            correlation_id = str(uuid.uuid4())
            base_metadata = {
                "seed": SEED_NAME,
                "seed_version": SEED_VERSION,
                "deterministic_random_seed": RANDOM_SEED,
                "numbering_year": NUMBERING_YEAR,
                "purpose": "arabic_uscr_shj_demo_data",
                "classification_scheme": "USCR-SHJ",
                "aggregation_count": AGGREGATION_COUNT,
                "record_count": EXPECTED_RECORD_COUNT,
                "component_count": EXPECTED_COMPONENT_COUNT,
                "aggregation_vital_count": 40,
                "record_vital_count": 160,
                "manifest_path": "examples/samples/docs/manifest.csv",
                "manifest_sha256": manifest_checksum,
            }
            for setting, value in (
                ("app.actor_type", "automated_process"),
                ("app.actor_name", "USCR-SHJ Arabic Demo Data Generator"),
                ("app.event_source", "seeding"),
                ("app.change_reason", "Generate deterministic classified Arabic demonstration records and digital content"),
                ("app.correlation_id", correlation_id),
                ("app.event_metadata", json.dumps(base_metadata, ensure_ascii=False)),
            ):
                connection.execute("SELECT set_config(%s, %s, true)", (setting, value))

            aggregation_ids: dict[int, int] = {}
            for aggregation in aggregations:
                aggregation_ids[aggregation.sequence] = connection.execute(
                    """INSERT INTO aggregations (
                           classification_id, aggregation_number, title, description,
                           date_created, date_opened, owning_org_unit_id, medium, is_vital
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,'digital',%s)
                       RETURNING id""",
                    (
                        aggregation.classification_id, aggregation.number, aggregation.title,
                        aggregation.description, aggregation.created, aggregation.created,
                        aggregation.owner_id, aggregation.is_vital,
                    ),
                ).fetchone()["id"]

            content_cache: dict[str, bytes] = {}
            for record in records:
                record_id = connection.execute(
                    """INSERT INTO records (
                           aggregation_id, record_number, title, description,
                           date_created, date_originated, medium, is_vital
                       ) VALUES (%s,%s,%s,%s,%s,%s,'digital',%s)
                       RETURNING id""",
                    (
                        aggregation_ids[record.aggregation_sequence], record.number,
                        record.title, record.description, record.created, record.created,
                        record.is_vital,
                    ),
                ).fetchone()["id"]
                for component_order, entry in enumerate(record.component_files, 1):
                    source_path = corpus_root / entry.relative_path
                    if entry.relative_path not in content_cache:
                        content_cache[entry.relative_path] = source_path.read_bytes()
                    content = content_cache[entry.relative_path]
                    mime_type = MIME_TYPES.get(entry.format) or mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
                    component_id = connection.execute(
                        """INSERT INTO digital_components (
                               record_id, component_order, file_name, date_created, date_originated,
                               mime_type, size_in_bytes, checksum_algo, checksum_value,
                               storage_backend, content_status
                           ) VALUES (%s,%s,%s,%s,%s,%s,%s,'sha256',%s,'postgresql','available')
                           RETURNING id""",
                        (
                            record_id, component_order, source_path.name, record.created, record.created,
                            mime_type, entry.size, entry.checksum,
                        ),
                    ).fetchone()["id"]
                    content_set_id = connection.execute(
                        """INSERT INTO digital_component_content_sets (
                               digital_component_id, status, size_in_bytes, segment_count,
                               checksum_algo, checksum_value, date_created, date_completed
                           ) VALUES (%s,'active',%s,1,'sha256',%s,%s,%s)
                           RETURNING id""",
                        (component_id, entry.size, entry.checksum, record.created, record.created),
                    ).fetchone()["id"]
                    connection.execute(
                        """INSERT INTO digital_component_blobs (
                               content_set_id, segment_no, segment_size, segment_checksum_algo,
                               segment_checksum_value, content, date_stored
                           ) VALUES (%s,0,%s,'sha256',%s,%s,%s)""",
                        (content_set_id, entry.size, entry.checksum, content, record.created),
                    )
                    connection.execute(
                        """UPDATE digital_components
                              SET active_content_set_id=%s, upload_completed_at=%s
                            WHERE id=%s""",
                        (content_set_id, record.created, component_id),
                    )
                    event_metadata = {
                        **base_metadata,
                        "record_number": record.number,
                        "topic": record.topic,
                        "source_path": f"examples/samples/docs/{entry.relative_path}",
                        "source_sha256": entry.checksum,
                        "file_name": source_path.name,
                        "mime_type": mime_type,
                        "size_in_bytes": entry.size,
                    }
                    connection.execute(
                        "SELECT append_domain_event('digital_component',%s,'CONTENT_UPLOADED',%s::jsonb)",
                        (component_id, json.dumps(event_metadata, ensure_ascii=False)),
                    )

            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            if not verify_existing(connection, aggregations, records, manifest_checksum):
                raise RuntimeError("post-seed verification failed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    created = seed(args.database_url, args.corpus.resolve())
    print("Seeded USCR-SHJ Arabic demo data." if created else "USCR-SHJ Arabic demo data already matches; no changes made.")


if __name__ == "__main__":
    main()
