#!/usr/bin/env python3
"""Extend the Wathiq corpus with email, markup, and presentation fixtures."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
from xml.etree import ElementTree as ET

from generate_corpus import TOPICS, TOPIC_LABELS, make_body, words
from msgforge import Message


FORMATS = (("eml", 40), ("msg", 40), ("xml", 40), ("pptx", 40), ("md", 40))


def write_eml(path: Path, spec: dict) -> None:
    message = EmailMessage(policy=SMTP)
    message["From"] = "records@example.invalid"
    message["To"] = "reviewer@example.invalid"
    message["Subject"] = f"{spec['title']} {spec['reference']}"
    message["Date"] = "Thu, 24 Sep 2026 10:30:00 +0400"
    message["Message-ID"] = f"<{spec['reference'].lower()}@example.invalid>"
    message.set_content(spec["body"], charset="utf-8")
    path.write_bytes(message.as_bytes())


def write_msg(path: Path, spec: dict) -> None:
    message = Message(
        subject=f"{spec['title']} {spec['reference']}",
        text_body=spec["body"],
        to=[("reviewer@example.invalid", "Records Reviewer")],
        sender=("records@example.invalid", "Wathiq Records"),
        sent=datetime(2026, 9, 24, 10, 30, tzinfo=timezone.utc),
    )
    message.save(path)


def write_xml(path: Path, spec: dict) -> None:
    root = ET.Element("wathiq-sample", {"id": str(spec["id"]), "language-mode": spec["language_mode"]})
    ET.SubElement(root, "reference").text = spec["reference"]
    ET.SubElement(root, "topic").text = spec["topic"]
    ET.SubElement(root, "title", {"lang": "en"}).text = spec["title"]
    ET.SubElement(root, "title", {"lang": "ar", "dir": "rtl"}).text = spec["arabic_title"]
    ET.SubElement(root, "body", {"lang": "mul"}).text = spec["body"]
    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    with path.open("wb") as stream:
        tree.write(stream, encoding="utf-8", xml_declaration=True)


def write_markdown(path: Path, spec: dict) -> None:
    body_tokens = words(spec["body"])
    paragraphs = [" ".join(body_tokens[i:i + 50]) for i in range(0, 200, 50)]
    path.write_text(
        f"# {spec['title']}\n\n## {spec['arabic_title']}\n\n"
        f"Synthetic reference `{spec['reference']}`\n\n" + "\n\n".join(paragraphs) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    manifest = root / "manifest.csv"
    with manifest.open(encoding="utf-8", newline="") as stream:
        existing = list(csv.DictReader(stream))
    if len(existing) not in {1000, 1200}:
        raise SystemExit(f"Expected a 1000- or 1200-row manifest, found {len(existing)}")
    existing = [row for row in existing if int(row["id"]) <= 1000]

    specs = []
    number = 1001
    for format_index, (extension, count) in enumerate(FORMATS):
        (root / extension).mkdir(exist_ok=True)
        for local_index in range(count):
            topic = TOPICS[(number - 1) % len(TOPICS)]
            mode = ("english", "arabic", "mixed")[(local_index + format_index) % 3]
            title, arabic_title = TOPIC_LABELS[topic]
            body, rare_en, rare_ar = make_body(number, topic, mode)
            stem = f"sample-{number:04d}-{topic}-{mode}"
            specs.append({
                "id": number, "format": extension, "path": f"{extension}/{stem}.{extension}",
                "stem": stem, "topic": topic, "language_mode": mode,
                "title": title, "arabic_title": arabic_title,
                "reference": f"WTHQ-{number:04d}", "body": body,
                "body_word_count": len(words(body)), "rare_english": rare_en,
                "rare_arabic": rare_ar, "unique_marker": f"wathiqrare{number:04d}",
            })
            number += 1
    assert len(specs) == 200 and all(spec["body_word_count"] == 200 for spec in specs)

    for spec in specs:
        destination = root / spec["path"]
        if spec["format"] == "eml": write_eml(destination, spec)
        elif spec["format"] == "msg": write_msg(destination, spec)
        elif spec["format"] == "xml": write_xml(destination, spec)
        elif spec["format"] == "md": write_markdown(destination, spec)

    pptx_specs = [spec for spec in specs if spec["format"] == "pptx"]
    (root / ".pptx-payload.json").write_text(json.dumps(pptx_specs, ensure_ascii=False), encoding="utf-8")

    new_rows = []
    for spec in specs:
        path = root / spec["path"]
        if spec["format"] == "pptx":
            size, digest = 0, "PENDING_PPTX_GENERATION"
        else:
            data = path.read_bytes(); size, digest = len(data), hashlib.sha256(data).hexdigest()
        new_rows.append({
            "id": str(spec["id"]), "format": spec["format"], "path": spec["path"],
            "topic": spec["topic"], "language_mode": spec["language_mode"],
            "body_word_count": str(spec["body_word_count"]), "rare_english": spec["rare_english"],
            "rare_arabic": spec["rare_arabic"], "unique_marker": spec["unique_marker"],
            "size_bytes": str(size), "sha256": digest,
        })
    rows = existing + new_rows
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"total_manifest_rows": len(rows), "extension_specs": len(specs)}))


if __name__ == "__main__":
    main()
