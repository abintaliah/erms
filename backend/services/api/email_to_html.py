from __future__ import annotations

import argparse
import html
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path


def _text(value: object | None) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "head"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _html_as_plain_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts).strip()


def _render_email(fields, body: str, attachment_names: list[str]) -> str:
    metadata = "".join(
        "<tr><th>" + html.escape(label) + "</th><td dir=\"auto\">"
        + html.escape(_text(value)) + "</td></tr>"
        for label, value in fields
        if value
    )
    attachments = ""
    if attachment_names:
        items = "".join(
            f'<li dir="auto">{html.escape(name)}</li>' for name in attachment_names
        )
        attachments = f"<h2>Attachments</h2><ul>{items}</ul>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{ margin: 18mm; }}
body {{ font-family: 'Noto Sans Arabic', 'Noto Sans', sans-serif; font-size: 11pt; line-height: 1.55; color: #111827; }}
table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
th {{ width: 90px; text-align: left; vertical-align: top; color: #475569; }}
td, th {{ padding: 4px 8px; border-bottom: 1px solid #e2e8f0; }}
.body {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
h2 {{ font-size: 12pt; margin-top: 18px; }}
</style></head><body>
<table>{metadata}</table>
<div class="body" dir="auto">{html.escape(body)}</div>
{attachments}
</body></html>"""


def build_msg_html(source: Path) -> str:
    """Extract an MSG into inert UTF-8 HTML without rendering active content."""
    import extract_msg

    message = extract_msg.openMsg(source)
    try:
        fields = (
            ("From", message.sender),
            ("To", message.to),
            ("Cc", message.cc),
            ("Date", message.date),
            ("Subject", message.subject),
        )
        attachment_names = [
            _text(getattr(attachment, "name", None)) or "Unnamed attachment"
            for attachment in message.attachments
            if not getattr(attachment, "hidden", False)
        ]
        return _render_email(fields, _text(message.body), attachment_names)
    finally:
        message.close()


def build_eml_html(source: Path) -> str:
    """Decode a MIME message and render only inert text and attachment names."""
    message = BytesParser(policy=policy.default).parsebytes(source.read_bytes())
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachment_names: list[str] = []
    for part in message.walk():
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            attachment_names.append(filename or "Unnamed attachment")
            continue
        if part.is_multipart():
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if content_type == "text/plain":
            plain_parts.append(str(content))
        else:
            html_parts.append(_html_as_plain_text(str(content)))
    body = "\n\n".join(plain_parts or html_parts)
    fields = (
        ("From", message.get("From")),
        ("To", message.get("To")),
        ("Cc", message.get("Cc")),
        ("Date", message.get("Date")),
        ("Subject", message.get("Subject")),
    )
    return _render_email(fields, body, attachment_names)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert an MSG or EML file to inert HTML")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.source.suffix.lower() == ".msg":
        rendered = build_msg_html(args.source)
    elif args.source.suffix.lower() == ".eml":
        rendered = build_eml_html(args.source)
    else:
        parser.error("source must have an .msg or .eml extension")
    args.destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
