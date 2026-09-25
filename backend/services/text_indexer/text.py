from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from lingua import Language, LanguageDetectorBuilder


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
CODE_RE = re.compile(r"\b(?:SELECT|FROM|WHERE|sha256)\b|[{};_=]", re.IGNORECASE)
CONTROL_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn"}
DETECTOR = LanguageDetectorBuilder.from_languages(Language.ENGLISH, Language.ARABIC).build()


@dataclass(frozen=True)
class ClassifiedChunk:
    text: str
    decision: str
    detected_language: str | None


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    value = "".join(
        character if character in "\n\t" or unicodedata.category(character) not in CONTROL_CATEGORIES else " "
        for character in value
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def classify(value: str) -> tuple[str, str | None]:
    if CODE_RE.search(value):
        return "code_like", None
    letters = [character for character in value if character.isalpha()]
    if len(letters) < 40:
        return "short", None
    latin = sum(bool(LATIN_RE.match(character)) for character in letters)
    arabic = sum(bool(ARABIC_RE.match(character)) for character in letters)
    supported = latin + arabic
    if supported / len(letters) < .90:
        return "unsupported_script", None
    dominant_ratio = max(latin, arabic) / max(1, supported)
    if dominant_ratio < .62:
        return "mixed", None
    best = DETECTOR.compute_language_confidence_values(value)[0]
    if best.value < .80:
        return "low_confidence", None
    if best.language == Language.ENGLISH:
        return "english", "en"
    return "arabic", "ar"


def chunks(value: str, target: int = 16_000, maximum: int = 20_000) -> list[ClassifiedChunk]:
    value = normalize(value)
    if not value:
        return []
    output: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", value):
        paragraph = paragraph.strip()
        while len(paragraph) > maximum:
            split = paragraph.rfind(" ", 0, maximum + 1)
            split = maximum if split < target // 2 else split
            if current:
                output.append(current)
                current = ""
            output.append(paragraph[:split].strip())
            paragraph = paragraph[split:].strip()
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > target:
            output.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        output.append(current)
    result = []
    for item in output:
        decision, language = classify(item)
        result.append(ClassifiedChunk(item, decision, language))
    return result
