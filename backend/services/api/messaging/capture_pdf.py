"""Deterministic, offline tagged PDFs; both independent profiles must pass."""

from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import monotonic
import xml.etree.ElementTree as ET
from .content import invalid
from .config import LIMITS

ASSETS = Path(__file__).with_name("pdf_assets")


def remaining(deadline):
    seconds = min(60, deadline - monotonic())
    if seconds <= 0:
        invalid("message_capture_renderer_unavailable", 503)
    return seconds


def render(title, content, language="en", direction="ltr", *, deadline=None):
    deadline = deadline or monotonic() + 180
    # Separate renderer process bounds a maliciously expensive rich-text layout.
    with tempfile.TemporaryDirectory(prefix="wathiq-capture-") as directory:
        root = Path(directory)
        source = root / "input.json"
        target = root / "component.pdf"
        source.write_text(
            json.dumps(
                {
                    "title": title,
                    "content": content,
                    "language": language,
                    "direction": direction,
                }
            ),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                [sys.executable, "-m", __name__, str(source), str(target)],
                capture_output=True,
                timeout=remaining(deadline),
            )
            if result.returncode or not target.exists():
                invalid("message_capture_render_failed", 409)
            if target.stat().st_size > LIMITS["CAPTURE_MAX_PDF_BYTES"]:
                invalid("message_capture_pdf_limit", 413)
            validate(target, deadline=deadline)
            return target.read_bytes()
        except (OSError, subprocess.TimeoutExpired):
            invalid("message_capture_renderer_unavailable", 503)


def validate(path, *, deadline=None):
    deadline = deadline or monotonic() + 120
    validator = os.environ.get("MESSAGING_PDF_VALIDATOR", "verapdf")
    for profile in ("2u", "ua1"):
        try:
            result = subprocess.run(
                [
                    validator,
                    "--format",
                    "xml",
                    "--maxfailures",
                    "1",
                    "-f",
                    profile,
                    str(path),
                ],
                capture_output=True,
                timeout=remaining(deadline),
            )
            tree = ET.fromstring(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ET.ParseError):
            invalid("message_capture_validator_unavailable", 503)
        reports = list(tree.iter("validationReport"))
        if (
            result.returncode
            or len(reports) != 1
            or reports[0].get("isCompliant") != "true"
        ):
            invalid("message_capture_pdf_nonconforming", 409)


def _finish(document, pdf):
    # WeasyPrint 68.1 emits block children of a list item directly below /LI.
    # PDF/UA requires them inside /LBody. Reparent the existing tagged objects
    # without changing content, marked-content IDs, or logical reading order.
    import pydyf

    objects = {obj.reference: obj for obj in pdf.objects}
    for item in tuple(pdf.objects):
        if not isinstance(item, dict) or item.get("S") != "/LI":
            continue
        children = pydyf.Array()
        current_body = None
        for reference in item.get("K", []):
            child = objects.get(reference) if isinstance(reference, bytes) else None
            if child is None or child.get("S") in ("/Lbl", "/LBody"):
                children.append(reference)
                if child is not None and child.get("S") == "/LBody":
                    current_body = child
                continue
            if current_body is None:
                current_body = pydyf.Dictionary(
                    {
                        "Type": "/StructElem",
                        "S": "/LBody",
                        "P": item.reference,
                        "K": pydyf.Array(),
                    }
                )
                if "Pg" in item:
                    current_body["Pg"] = item["Pg"]
                pdf.add_object(current_body)
                children.append(current_body.reference)
            current_body["K"].append(reference)
            child["P"] = current_body.reference
        item["K"] = children
    for prefix, uri in [
        ("pdfuaid", "http://www.aiim.org/pdfua/ns/id/"),
        ("pdfaExtension", "http://www.aiim.org/pdfa/ns/extension/"),
        ("pdfaSchema", "http://www.aiim.org/pdfa/ns/schema#"),
        ("pdfaProperty", "http://www.aiim.org/pdfa/ns/property#"),
    ]:
        ET.register_namespace(prefix, uri)
    for obj in pdf.objects:
        if getattr(obj, "extra", {}).get("Type") == "/Metadata":
            root = ET.fromstring(obj.stream[0])
            rdf = root.find("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF")
            desc = ET.SubElement(
                rdf,
                "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description",
                {"{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about": ""},
            )
            ET.SubElement(desc, "{http://www.aiim.org/pdfua/ns/id/}part").text = "1"
            rdf.append(ET.fromstring((ASSETS / "pdfua-extension.xml").read_bytes()))
            obj.stream = [ET.tostring(root, encoding="utf-8")]


def _worker(source, target):
    from weasyprint import HTML, default_url_fetcher

    value = json.loads(Path(source).read_text())
    allowed = {p.as_uri() for p in ASSETS.glob("*.ttf")}

    def fetch(url, *args, **kwargs):
        if url not in allowed:
            raise ValueError("External PDF resources are forbidden")
        return default_url_fetcher(url, *args, **kwargs)

    fonts = "".join(
        f'@font-face{{font-family:Changa{kind};src:url("{(ASSETS/name).as_uri()}")}}'
        for kind, name in [
            ("Latin", "changa-latin.ttf"),
            ("Extended", "changa-latin-ext.ttf"),
            ("Arabic", "changa-arabic.ttf"),
        ]
    )
    css = (
        fonts
        + """@page{size:A4;margin:22mm} body{font-family:ChangaLatin,ChangaExtended,ChangaArabic;font-size:11pt;line-height:1.65;color:#172b42;overflow-wrap:anywhere} h1{font-size:20pt;color:#164a70} h2{font-size:14pt;color:#164a70} h3{font-size:12pt} p,li{orphans:3;widows:3} pre,code{font-family:ChangaLatin,ChangaExtended,ChangaArabic;white-space:pre-wrap} a{color:#164a70;text-decoration:underline} .field{margin:3pt 0}"""
    )
    html = f'<!doctype html><html lang="{escape(value["language"],quote=True)}" dir="{value["direction"]}"><head><meta charset="utf-8"><title>{escape(value["title"])}</title><style>{css}</style></head><body><h1>{escape(value["title"])}</h1>{value["content"]}</body></html>'
    HTML(string=html, url_fetcher=fetch).write_pdf(
        target,
        pdf_variant="pdf/a-2u",
        pdf_tags=True,
        finisher=_finish,
        pdf_identifier=sha256(html.encode()).hexdigest().encode(),
    )


if __name__ == "__main__":
    _worker(sys.argv[1], sys.argv[2])
