#!/usr/bin/env python3
"""Run reproducible Phase 0 Tika, Tesseract, language, and robustness benchmarks."""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import resource
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "phase0-benchmark-results.json"
TIKA = os.environ.get("TIKA_BINARY", "tika")
TESSERACT = os.environ.get("TESSERACT_BINARY", "tesseract")

from lingua import Language, LanguageDetectorBuilder  # noqa: E402

from generate_corpus import make_body  # noqa: E402


TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def tokens(text: str, script: str) -> list[str]:
    found = [token.casefold() for token in TOKEN_RE.findall(text)]
    if script == "arabic":
        return [token for token in found if ARABIC_RE.search(token)]
    return [token for token in found if LATIN_RE.search(token)]


def multiset_recall(expected: list[str], actual: list[str]) -> float:
    expected_counts, actual_counts = Counter(expected), Counter(actual)
    matched = sum(min(count, actual_counts[token]) for token, count in expected_counts.items())
    return matched / max(1, sum(expected_counts.values()))


def command_version(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    return (result.stdout or result.stderr).splitlines()[0]


def run(command: list[str], timeout: int = 60) -> tuple[subprocess.CompletedProcess[str], float, int]:
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    started = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return result, elapsed, max(0, after - before)


def selected_rows() -> list[dict[str, str]]:
    rows = list(csv.DictReader((ROOT / "manifest.csv").open(encoding="utf-8")))
    selected = []
    for fmt in ("docx", "xlsx", "txt", "pdf", "html", "eml", "msg", "xml", "pptx", "md"):
        for mode in ("english", "arabic", "mixed"):
            selected.append(next(row for row in rows if row["format"] == fmt and row["language_mode"] == mode))
    return selected


def tika_benchmark() -> dict:
    cases = []
    for row in selected_rows():
        path = ROOT / row["path"]
        result, elapsed, rss_delta = run([TIKA, "--text", str(path)], timeout=60)
        body, _, _ = make_body(int(row["id"]), row["topic"], row["language_mode"])
        cases.append({
            "path": row["path"], "format": row["format"], "language_mode": row["language_mode"],
            "returncode": result.returncode, "elapsed_seconds": round(elapsed, 3), "rss_delta_platform_units": rss_delta,
            "english_word_recall": round(multiset_recall(tokens(body, "english"), tokens(result.stdout, "english")), 4),
            "arabic_word_recall": round(multiset_recall(tokens(body, "arabic"), tokens(result.stdout, "arabic")), 4),
            "marker_found": row["unique_marker"].casefold() in result.stdout.casefold(),
        })
    successful = [case for case in cases if case["returncode"] == 0]
    return {
        "cases": cases,
        "summary": {
            "case_count": len(cases), "successful": len(successful),
            "marker_recall": round(sum(case["marker_found"] for case in cases) / len(cases), 4),
            "english_word_recall": round(sum(case["english_word_recall"] for case in cases) / len(cases), 4),
            "arabic_word_recall": round(sum(case["arabic_word_recall"] for case in cases) / len(cases), 4),
            "median_elapsed_seconds": round(sorted(case["elapsed_seconds"] for case in cases)[len(cases) // 2], 3),
            "max_elapsed_seconds": max(case["elapsed_seconds"] for case in cases),
        },
    }


def ocr_benchmark() -> dict:
    rows = list(csv.DictReader((ROOT / "manifest.csv").open(encoding="utf-8")))
    chosen = [
        row for row in rows
        if row["format"] in {"png", "jpeg"} and row["language_mode"] in {"english", "arabic", "mixed"}
    ][:36]
    cases = []
    for row in chosen:
        path = ROOT / row["path"]
        result, elapsed, rss_delta = run([TESSERACT, str(path), "stdout", "-l", "eng+ara", "--psm", "6"], timeout=60)
        body, _, _ = make_body(int(row["id"]), row["topic"], row["language_mode"])
        cases.append({
            "path": row["path"], "language_mode": row["language_mode"], "returncode": result.returncode,
            "elapsed_seconds": round(elapsed, 3), "rss_delta_platform_units": rss_delta,
            "english_word_recall": round(multiset_recall(tokens(body, "english"), tokens(result.stdout, "english")), 4),
            "arabic_word_recall": round(multiset_recall(tokens(body, "arabic"), tokens(result.stdout, "arabic")), 4),
            "marker_found": row["unique_marker"].casefold() in result.stdout.casefold(),
        })
    english = [case for case in cases if case["language_mode"] == "english"]
    arabic = [case for case in cases if case["language_mode"] == "arabic"]
    return {
        "cases": cases,
        "summary": {
            "case_count": len(cases), "successful": sum(case["returncode"] == 0 for case in cases),
            "english_word_recall": round(sum(case["english_word_recall"] for case in english) / len(english), 4),
            "arabic_word_recall": round(sum(case["arabic_word_recall"] for case in arabic) / len(arabic), 4),
            "marker_recall": round(sum(case["marker_found"] for case in cases) / len(cases), 4),
            "median_elapsed_seconds": round(sorted(case["elapsed_seconds"] for case in cases)[len(cases) // 2], 3),
            "max_elapsed_seconds": max(case["elapsed_seconds"] for case in cases),
        },
    }


def supplementary_format_benchmark() -> dict:
    expected = {
        "sample-0001-finance-english.doc": "wathiqrare0001",
        "sample-0001-finance-english.odt": "wathiqrare0001",
        "sample-0146-human-resources-english.xls": "wathiqrare0146",
        "sample-0146-human-resources-english.ods": "wathiqrare0146",
        "sample-1121-finance-english.ppt": "wathiqrare1121",
        "sample-1121-finance-english.odp": "wathiqrare1121",
        "sample-0288-procurement-english.rtf": "wathiqrare0288",
        "sample-english.csv": "wathiqrare0288",
        "sample-arabic.tiff": "wathiqrare0573",
    }
    cases = []
    for name, marker in expected.items():
        path = ROOT / "phase0-formats" / name
        result, elapsed, _ = run([TIKA, "--text", str(path)], timeout=60)
        cases.append({
            "path": str(path.relative_to(ROOT)), "returncode": result.returncode,
            "elapsed_seconds": round(elapsed, 3), "marker_found": marker in result.stdout.casefold(),
        })
    return {
        "cases": cases,
        "summary": {
            "case_count": len(cases), "successful": sum(case["returncode"] == 0 for case in cases),
            "marker_recall": round(sum(case["marker_found"] for case in cases) / len(cases), 4),
        },
    }


def classify(detector, text: str) -> str:
    if re.search(r"\b(?:SELECT|FROM|WHERE|sha256)\b|[{};_=]", text, re.IGNORECASE):
        return "simple"
    letters = [character for character in text if character.isalpha()]
    if len(letters) < 40:
        return "simple"
    latin = sum(bool(LATIN_RE.match(character)) for character in letters)
    arabic = sum(bool(ARABIC_RE.match(character)) for character in letters)
    supported = latin + arabic
    if supported / len(letters) < 0.90:
        return "simple"
    dominant_ratio = max(latin, arabic) / max(1, supported)
    if dominant_ratio < 0.62:
        return "mixed"
    confidences = detector.compute_language_confidence_values(text)
    best = confidences[0]
    if best.value < 0.80:
        return "simple"
    return "english" if best.language == Language.ENGLISH else "arabic"


def language_benchmark() -> dict:
    detector = LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.ARABIC).build()
    rows = list(csv.DictReader((ROOT / "manifest.csv").open(encoding="utf-8")))
    cases = []
    for row in rows[:300]:
        body, _, _ = make_body(int(row["id"]), row["topic"], row["language_mode"])
        actual = classify(detector, body)
        cases.append({"path": row["path"], "expected": row["language_mode"], "actual": actual})
    edge_expected = {
        "english-short.txt": "simple", "arabic-short.txt": "simple", "balanced-mixed.txt": "mixed",
        "numeric-only.txt": "simple", "code-like.txt": "simple", "unknown-language.txt": "simple",
        "symbols-only.txt": "simple",
    }
    for name, expected in edge_expected.items():
        actual = classify(detector, (ROOT / "phase0-language-edge" / name).read_text(encoding="utf-8"))
        cases.append({"path": f"phase0-language-edge/{name}", "expected": expected, "actual": actual})
    correct = sum(case["expected"] == case["actual"] for case in cases)
    return {"cases": cases, "summary": {"case_count": len(cases), "correct": correct, "accuracy": round(correct / len(cases), 4)}}


def robustness_benchmark() -> dict:
    paths = sorted((ROOT / "phase0-corrupt").glob("*")) + sorted((ROOT / "phase0-protected").glob("*"))
    cases = []
    for path in paths:
        try:
            # The benchmark harness supplies the hard wall timeout. Production
            # process/container isolation is delivered and tested in Phase 2.
            result, elapsed, rss_delta = run([TIKA, "--text", str(path)], timeout=15)
            cases.append({
                "path": str(path.relative_to(ROOT)), "bounded": elapsed <= 15, "elapsed_seconds": round(elapsed, 3),
                "returncode": result.returncode, "rss_delta_platform_units": rss_delta, "output_characters": len(result.stdout),
            })
        except subprocess.TimeoutExpired:
            cases.append({"path": str(path.relative_to(ROOT)), "bounded": False, "elapsed_seconds": 15, "returncode": None})
    return {"cases": cases, "summary": {"case_count": len(cases), "bounded": sum(case["bounded"] for case in cases)}}


def main() -> None:
    result = {
        "environment": {
            "platform": platform.platform(), "python": platform.python_version(),
            "tika": command_version([TIKA, "--version"]),
            "tesseract": command_version([TESSERACT, "--version"]),
            "languages": subprocess.run([TESSERACT, "--list-langs"], capture_output=True, text=True).stdout.splitlines()[1:],
            "language_detector": "lingua-language-detector 2.1.1; models restricted to English and Arabic",
        },
        "tika_native_extraction": tika_benchmark(),
        "supplementary_formats": supplementary_format_benchmark(),
        "tesseract_ocr": ocr_benchmark(),
        "language_detection": language_benchmark(),
        "robustness": robustness_benchmark(),
    }
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value.get("summary") for key, value in result.items() if isinstance(value, dict) and "summary" in value}, indent=2))


if __name__ == "__main__":
    main()
