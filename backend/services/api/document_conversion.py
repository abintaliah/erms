from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import integer_environment


class ConversionUnavailable(RuntimeError):
    pass


class UnsupportedPreview(RuntimeError):
    pass


CONVERTIBLE_EXTENSIONS = {
    ".doc", ".docx", ".odt", ".rtf",
    ".xls", ".xlsx", ".ods", ".csv",
    ".ppt", ".pptx", ".odp",
}


def _libreoffice_binary() -> str:
    configured = os.getenv("LIBREOFFICE_BINARY", "").strip()
    binary = configured or shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        raise ConversionUnavailable(
            "LibreOffice is not available on the API server; download the original or install LibreOffice to enable this preview"
        )
    return binary


def pdf_rendition(content: bytes, file_name: str, mime_type: str) -> tuple[bytes, str]:
    """Return PDF bytes and the rendering method used."""
    if mime_type.lower() == "application/pdf" or content.startswith(b"%PDF-"):
        return content, "original"

    suffix = Path(file_name).suffix.lower()
    if suffix not in CONVERTIBLE_EXTENSIONS:
        raise UnsupportedPreview(f"in-app preview is not supported for {suffix or mime_type}")

    timeout = integer_environment("DOCUMENT_CONVERSION_TIMEOUT_SECONDS", 60, minimum=1)
    maximum = integer_environment("MAX_RENDITION_SIZE_BYTES", 100 * 1024 * 1024, minimum=1)
    with tempfile.TemporaryDirectory(prefix="erms-rendition-") as temporary:
        workspace = Path(temporary)
        source = workspace / f"source{suffix}"
        output = workspace / "output"
        profile = workspace / "profile"
        output.mkdir()
        profile.mkdir()
        source.write_bytes(content)
        command = [
            _libreoffice_binary(),
            "--headless", "--nologo", "--nodefault", "--nolockcheck", "--norestore",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to", "pdf", "--outdir", str(output), str(source),
        ]
        try:
            completed = subprocess.run(
                command, check=False, capture_output=True, timeout=timeout,
                env={**os.environ, "SAL_DISABLE_OPENCL": "1"},
            )
        except subprocess.TimeoutExpired as error:
            raise ConversionUnavailable("document conversion timed out") from error
        rendition = output / "source.pdf"
        if completed.returncode != 0 or not rendition.is_file():
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise ConversionUnavailable(f"LibreOffice could not convert this document{': ' + detail if detail else ''}")
        if rendition.stat().st_size > maximum:
            raise ConversionUnavailable("generated PDF exceeds the configured rendition size limit")
        return rendition.read_bytes(), "libreoffice"
