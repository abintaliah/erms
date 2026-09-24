from __future__ import annotations

import argparse
import codecs
import html
import re
from pathlib import Path


_ENCODING_DECLARATION = re.compile(
    br"<\?xml[^>]*\bencoding\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


def decode_xml_source(content: bytes) -> str:
    """Decode XML for source display without parsing or resolving its contents."""
    if content.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        encoding = "utf-32"
    elif content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        encoding = "utf-16"
    elif content.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    else:
        match = _ENCODING_DECLARATION.search(content[:1024])
        encoding = match.group(1).decode("ascii", errors="replace") if match else "utf-8"
        try:
            codecs.lookup(encoding)
        except LookupError:
            encoding = "utf-8"
    return content.decode(encoding, errors="replace")


def build_xml_html(source: Path) -> str:
    escaped = html.escape(decode_xml_source(source.read_bytes()))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ margin: 15mm; }}
body {{ color: #111827; }}
h1 {{ font: 600 13pt 'Noto Sans Arabic', 'Noto Sans', sans-serif; margin: 0 0 12px; }}
pre {{ font: 9pt/1.5 'Noto Sans Mono', 'Noto Sans Arabic', monospace; white-space: pre-wrap; overflow-wrap: anywhere; tab-size: 2; }}
</style></head><body>
<h1>XML source</h1><pre dir="auto">{escaped}</pre>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render XML source as inert UTF-8 HTML")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.write_text(build_xml_html(args.source), encoding="utf-8")


if __name__ == "__main__":
    main()
