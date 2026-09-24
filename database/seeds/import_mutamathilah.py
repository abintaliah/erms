#!/usr/bin/env python3
"""Import the example Mutamathilah XML file plan as an audited draft scheme."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

import psycopg


SEED_NAME = "025_seed_mutamathilah_classification_scheme"
DEFAULT_XML = Path(__file__).resolve().parents[2] / "examples/fileplans/mutamathilah.xml"
DISPOSITIONS = {
    "Destroy": "destruction",
    "Permanent Preservation": "transfer_to_external_archive",
    "Selective Preservation": "selective_preservation",
    "Retain as Local Archives": "retain_as_local_archives",
}


def publication_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("date_published must be a valid ISO-8601 timestamp") from error


def validate(root: ET.Element) -> tuple[list[ET.Element], list[ET.Element]]:
    if root.tag != "ClassificationScheme":
        raise ValueError("root element must be ClassificationScheme")
    for attribute in ("code", "title_en"):
        if not (root.get(attribute) or "").strip():
            raise ValueError(f"scheme {attribute} is required")
    if not (root.get("name") or "").strip():
        raise ValueError("scheme Arabic name is required for description mapping")

    classifications = list(root.iter("Classification"))
    codes: set[str] = set()
    terminals: list[ET.Element] = []
    for classification in classifications:
        code = (classification.get("code") or "").strip()
        title_en = (classification.get("title_en") or "").strip()
        title_ar = (classification.get("title_ar") or "").strip()
        if not code or not title_en or not title_ar:
            raise ValueError(
                f"classification {code or '<unknown>'} requires code, title_en and title_ar"
            )
        if code in codes:
            raise ValueError(f"duplicate classification code: {code}")
        codes.add(code)

        children = classification.findall("Classification")
        rules = classification.findall("Retention")
        if children and rules:
            raise ValueError(f"branch classification {code} must not define retention")
        if not children:
            if len(rules) != 1:
                raise ValueError(f"terminal classification {code} must define exactly one retention rule")
            rule = rules[0]
            for attribute in ("current", "intermediate"):
                try:
                    if int(rule.get(attribute, "")) < 0:
                        raise ValueError
                except ValueError as error:
                    raise ValueError(
                        f"classification {code} has invalid {attribute} retention period"
                    ) from error
            if rule.get("disposition") not in DISPOSITIONS:
                raise ValueError(
                    f"classification {code} has unsupported disposition {rule.get('disposition')!r}"
                )
            terminals.append(classification)
    return classifications, terminals


def import_scheme(database_url: str, xml_path: Path) -> bool:
    raw_xml = xml_path.read_bytes()
    root = ET.fromstring(raw_xml)
    classifications, terminals = validate(root)
    checksum = hashlib.sha256(raw_xml).hexdigest()
    scheme_code = root.attrib["code"].strip()
    # This example file plan is intended for an Arabic-speaking demo audience:
    # Arabic values are the user-visible titles and English values are retained
    # as descriptions.
    scheme_title = root.attrib["name"].strip()
    scheme_description = root.attrib["title_en"].strip()
    published = publication_date(root.get("date_published"))
    correlation_id = str(uuid.uuid4())
    reason = (
        "Import the Unified Scheme for Common Records of the Emirate of Sharjah "
        "from the approved example XML file plan"
    )
    metadata = {
        "seed": SEED_NAME,
        "operation": "xml_classification_scheme_seed",
        "basis": "greenfield example data explicitly approved by the user",
        "source_file": xml_path.name,
        "source_sha256": checksum,
        "scheme_code": scheme_code,
        "scheme_version": root.get("version"),
        "publication_policy": "draft_when_date_published_is_absent",
        "title_mapping": {
            "title": "Arabic scheme name / classification title_ar",
            "description": "scheme title_en / classification title_en",
        },
        "ignored_xml_fields": [],
        "expected_counts": {
            "root_classifications": len(root.findall("Classification")),
            "classifications": len(classifications),
            "terminal_classifications": len(terminals),
            "retention_rules": len(terminals),
            "audit_events": 1 + len(classifications) + len(terminals),
        },
    }

    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            collision = connection.execute(
                """SELECT code, title FROM classification_schemes
                    WHERE lower(code)=lower(%s) OR lower(title)=lower(%s)""",
                (scheme_code, scheme_title),
            ).fetchone()
            if collision:
                if collision[0].lower() == scheme_code.lower() and collision[1].lower() == scheme_title.lower():
                    return False
                raise ValueError(
                    f"classification scheme collision: {collision[0]} — {collision[1]}"
                )

            for setting, value in (
                ("app.actor_type", "automated_process"),
                ("app.event_source", "seeding"),
                ("app.change_reason", reason),
                ("app.correlation_id", correlation_id),
                ("app.event_metadata", json.dumps(metadata, ensure_ascii=False)),
            ):
                connection.execute("SELECT set_config(%s, %s, true)", (setting, value))

            scheme_id = connection.execute(
                """INSERT INTO classification_schemes (
                       code, title, description, edition, date_published
                   ) VALUES (%s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    scheme_code,
                    scheme_title,
                    scheme_description,
                    (root.get("version") or "").strip() or None,
                    published,
                ),
            ).fetchone()[0]

            ids_by_element: dict[ET.Element, int] = {}

            def insert_classification(element: ET.Element, parent_id: int | None) -> None:
                children = element.findall("Classification")
                classification_id = connection.execute(
                    """INSERT INTO classifications (
                           classification_scheme_id, parent_classification_id,
                           code, title, description, is_terminal
                       ) VALUES (%s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        scheme_id,
                        parent_id,
                        element.attrib["code"].strip(),
                        element.attrib["title_ar"].strip(),
                        element.attrib["title_en"].strip(),
                        not children,
                    ),
                ).fetchone()[0]
                ids_by_element[element] = classification_id
                for child in children:
                    insert_classification(child, classification_id)

            for root_classification in root.findall("Classification"):
                insert_classification(root_classification, None)

            for terminal in terminals:
                rule = terminal.find("Retention")
                assert rule is not None
                connection.execute(
                    """INSERT INTO classification_retention_rules (
                           classification_id, current_period_years,
                           intermediate_period_years, final_disposition
                       ) VALUES (%s, %s, %s, %s)""",
                    (
                        ids_by_element[terminal],
                        int(rule.attrib["current"]),
                        int(rule.attrib["intermediate"]),
                        DISPOSITIONS[rule.attrib["disposition"]],
                    ),
                )

            connection.execute("SET CONSTRAINTS ALL IMMEDIATE")
            actual = connection.execute(
                """SELECT
                       count(*) AS classifications,
                       count(*) FILTER (WHERE parent_classification_id IS NULL) AS roots,
                       count(*) FILTER (WHERE is_terminal) AS terminals,
                       (SELECT count(*) FROM classification_retention_rules AS rule
                         JOIN classifications AS child ON child.id=rule.classification_id
                        WHERE child.classification_scheme_id=%s) AS rules
                     FROM classifications WHERE classification_scheme_id=%s""",
                (scheme_id, scheme_id),
            ).fetchone()
            expected = (len(classifications), len(root.findall("Classification")), len(terminals), len(terminals))
            if tuple(actual) != expected:
                raise RuntimeError(f"import count mismatch: expected {expected}, got {tuple(actual)}")

            audit_count = connection.execute(
                "SELECT count(*) FROM event_history WHERE correlation_id=%s::uuid",
                (correlation_id,),
            ).fetchone()[0]
            if audit_count != metadata["expected_counts"]["audit_events"]:
                raise RuntimeError(
                    f"audit count mismatch: expected {metadata['expected_counts']['audit_events']}, "
                    f"got {audit_count}"
                )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--xml", type=Path, default=DEFAULT_XML)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")
    imported = import_scheme(args.database_url, args.xml.resolve())
    print("Imported USCR-SHJ." if imported else "USCR-SHJ was already imported; no changes made.")


if __name__ == "__main__":
    main()
