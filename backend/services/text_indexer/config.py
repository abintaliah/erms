from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


MIME_TYPES = (
    "application/pdf", "application/rtf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "message/rfc822", "application/vnd.ms-outlook", "text/plain", "text/csv",
    "text/html", "application/xhtml+xml", "application/xml", "text/xml",
    "text/markdown", "image/png", "image/jpeg", "image/tiff",
)


def _integer(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    api_url: str
    api_key: str
    worker_id: str
    tika_home: Path
    claim_batch_size: int
    poll_seconds: int
    heartbeat_seconds: int
    extraction_timeout_seconds: int
    max_input_bytes: int
    max_extracted_characters: int
    chunk_target_characters: int
    chunk_max_characters: int
    max_pages: int
    max_temp_bytes: int
    temp_root: Path
    stale_temp_hours: int
    temp_sweep_limit: int

    @classmethod
    def from_environment(cls) -> "Settings":
        api_url = os.environ["TEXT_INDEXER_API_URL"].rstrip("/")
        parsed = urlparse(api_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("TEXT_INDEXER_API_URL must use HTTP or HTTPS")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("unencrypted text-indexer API access is allowed only on loopback")
        api_key = os.environ["TEXT_INDEXER_API_KEY"]
        if not api_key.startswith("wti_"):
            raise ValueError("TEXT_INDEXER_API_KEY is not a Wathiq text-indexer key")
        return cls(
            api_url=api_url, api_key=api_key,
            worker_id=os.getenv("TEXT_INDEXER_WORKER_ID", f"local-{os.getpid()}"),
            tika_home=Path(os.environ["TEXT_INDEXER_TIKA_HOME"]).resolve(),
            claim_batch_size=_integer("TEXT_INDEXER_CLAIM_BATCH_SIZE", 1),
            poll_seconds=_integer("TEXT_INDEXER_POLL_SECONDS", 5),
            heartbeat_seconds=_integer("TEXT_INDEXER_HEARTBEAT_SECONDS", 60),
            extraction_timeout_seconds=_integer("TEXT_INDEXER_EXTRACTION_TIMEOUT_SECONDS", 120),
            max_input_bytes=_integer("TEXT_INDEXER_MAX_INPUT_BYTES", 50 * 1024 * 1024),
            max_extracted_characters=_integer("TEXT_INDEXER_MAX_EXTRACTED_CHARACTERS", 5_000_000),
            chunk_target_characters=_integer("TEXT_INDEXER_CHUNK_TARGET_CHARACTERS", 16_000),
            chunk_max_characters=_integer("TEXT_INDEXER_CHUNK_MAX_CHARACTERS", 20_000),
            max_pages=_integer("TEXT_INDEXER_MAX_PAGES", 1_000),
            max_temp_bytes=_integer("TEXT_INDEXER_MAX_TEMP_BYTES", 1024 * 1024 * 1024),
            temp_root=Path(os.getenv("TEXT_INDEXER_TEMP_DIR",str(Path(tempfile.gettempdir())/"wathiq-text-indexer"))).resolve(),
            stale_temp_hours=_integer("TEXT_INDEXER_STALE_TEMP_HOURS",24),
            temp_sweep_limit=_integer("TEXT_INDEXER_TEMP_SWEEP_LIMIT",100),
        )
