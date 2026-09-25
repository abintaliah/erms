#!/usr/bin/env python3
"""Generate deterministic Phase 0 edge, robustness, and format fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parent
SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)


def convert(source: Path, extension: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(SOFFICE), "--headless", "--convert-to", extension, "--outdir", str(output_dir), str(source)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    result = output_dir / f"{source.stem}.{extension}"
    if not result.is_file():
        raise RuntimeError(f"LibreOffice did not create {result}")
    return result


def generate_formats() -> None:
    target = ROOT / "phase0-formats"
    convert(ROOT / "docx/sample-0001-finance-english.docx", "odt", target)
    convert(ROOT / "docx/sample-0001-finance-english.docx", "doc", target)
    convert(ROOT / "xlsx/sample-0146-human-resources-english.xlsx", "ods", target)
    convert(ROOT / "xlsx/sample-0146-human-resources-english.xlsx", "xls", target)
    convert(ROOT / "pptx/sample-1121-finance-english.pptx", "odp", target)
    convert(ROOT / "pptx/sample-1121-finance-english.pptx", "ppt", target)
    convert(ROOT / "txt/sample-0288-procurement-english.txt", "rtf", target)
    shutil.copyfile(ROOT / "txt/sample-0288-procurement-english.txt", target / "sample-english.csv")
    image = Image.open(ROOT / "png/sample-0573-records-management-arabic.png").convert("RGB")
    image.save(target / "sample-arabic.tiff", compression="tiff_deflate")


def generate_scanned_pdfs() -> None:
    target = ROOT / "phase0-scanned-pdf"
    target.mkdir(parents=True, exist_ok=True)
    sources = {
        "scanned-english.pdf": ROOT / "png/sample-0575-information-technology-english.png",
        "scanned-arabic.pdf": ROOT / "png/sample-0573-records-management-arabic.png",
        "scanned-mixed.pdf": ROOT / "png/sample-0574-project-management-mixed.png",
    }
    for name, source in sources.items():
        Image.open(source).convert("RGB").save(target / name, "PDF", resolution=300.0)


def generate_protected_and_corrupt() -> None:
    protected = ROOT / "phase0-protected"
    protected.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(ROOT / "pdf/sample-0430-project-management-english.pdf")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("wathiq-phase0-fixture-password", algorithm="AES-256")
    with (protected / "password-protected.pdf").open("wb") as stream:
        writer.write(stream)

    corrupt = ROOT / "phase0-corrupt"
    write(corrupt / "truncated.pdf", b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    write(corrupt / "invalid.docx", b"PK\x03\x04WATHIQ_CORRUPT_DOCX")
    write(corrupt / "invalid.xlsx", b"PK\x03\x04WATHIQ_CORRUPT_XLSX")
    write(corrupt / "invalid.png", b"\x89PNG\r\n\x1a\nWATHIQ_CORRUPT_PNG")


def generate_adversarial() -> None:
    target = ROOT / "phase0-adversarial"
    write(
        target / "external-entity.xml",
        '<?xml version="1.0"?><!DOCTYPE data [<!ENTITY probe SYSTEM "file:///etc/passwd">]>'
        "<data>&probe;</data>\n",
    )
    write(
        target / "active-external-content.html",
        "<!doctype html><script>document.location='https://example.invalid/leak'</script>"
        '<img src="https://example.invalid/tracker.png"><p>Safe visible Wathiq text.</p>\n',
    )
    write(target / "pathological-whitespace.txt", "Wathiq" + (" \t\r\n" * 250_000) + "terminal marker\n")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target / "high-compression.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("repeated.txt", b"WATHIQ-ZIP-BOMB-PROBE\n" * 2_000_000)
    nested = target / "nested-archives.zip"
    payload = b"nested Wathiq archive fixture"
    for depth in range(8, 0, -1):
        temporary = target / f".level-{depth}.zip"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"level-{depth}.bin", payload)
        payload = temporary.read_bytes()
        temporary.unlink()
    nested.write_bytes(payload)


def generate_language_edges() -> None:
    target = ROOT / "phase0-language-edge"
    fixtures = {
        "english-short.txt": "Approved budget.",
        "arabic-short.txt": "الميزانية المعتمدة.",
        "balanced-mixed.txt": (
            "Approved budget and expenditure records require review and documented authorization. "
            "تتطلب سجلات الميزانية المعتمدة والمصروفات مراجعة وتفويضا موثقا."
        ),
        "numeric-only.txt": "2026 1048576 3.14159 000042",
        "code-like.txt": "SELECT record_id FROM records WHERE status = 'active'; sha256 deadbeef",
        "unknown-language.txt": "承認された予算と支出の記録",
        "symbols-only.txt": "---- //// ++++ **** ....",
    }
    for name, content in fixtures.items():
        write(target / name, content + "\n")


def generate_oversized() -> None:
    target = ROOT / "phase0-oversized/oversized-52mib.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    marker = b"WATHIQ OVERSIZED INPUT LIMIT FIXTURE\n"
    with target.open("wb") as stream:
        remaining = 52 * 1024 * 1024
        while remaining:
            chunk = marker[: min(len(marker), remaining)]
            stream.write(chunk)
            remaining -= len(chunk)


def write_manifest() -> None:
    prefixes = (
        "phase0-adversarial", "phase0-corrupt", "phase0-formats", "phase0-language-edge",
        "phase0-oversized", "phase0-protected", "phase0-scanned-pdf",
    )
    rows = []
    for prefix in prefixes:
        for path in sorted((ROOT / prefix).rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                rows.append({
                    "path": str(path.relative_to(ROOT)),
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
    write(ROOT / "phase0-edge-manifest.json", json.dumps({"files": rows}, indent=2) + "\n")


def main() -> None:
    generate_formats()
    generate_scanned_pdfs()
    generate_protected_and_corrupt()
    generate_adversarial()
    generate_language_edges()
    generate_oversized()
    write_manifest()
    print(f"generated {len(json.loads((ROOT / 'phase0-edge-manifest.json').read_text())['files'])} fixtures")


if __name__ == "__main__":
    main()
