"""Conservative HTML serialization: input markup is never copied verbatim."""

from html import escape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import unquote, urlsplit
from uuid import UUID
from fastapi import HTTPException

BODY_BYTES = 65536
REQUEST_BODY_BYTES = 131072
TAGS = frozenset(
    (
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "ul",
        "ol",
        "li",
        "blockquote",
        "h1",
        "h2",
        "h3",
        "pre",
        "code",
        "a",
        "span",
    )
)
INTERNAL_PATH = re.compile(
    r"/(?:api/v1/)?(?:aggregations|records|digital-components)(?:/|$)", re.I
)


def invalid(code: str, status: int = 422):
    detail = {"code": code}
    if code in CAPTURE_ERROR_KEYS:
        detail["message_key"] = CAPTURE_ERROR_KEYS[code]
    raise HTTPException(status_code=status, detail=detail)


def subject(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > 255:
        invalid("message_subject_invalid")
    return value


class Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.tokens = []
        self.suppressed = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if self.suppressed:
            if tag not in (
                "br",
                "img",
                "hr",
                "input",
                "meta",
                "link",
                "wbr",
                "source",
                "embed",
            ):
                self.suppressed.append(tag)
            return
        if tag in ("script", "style", "iframe", "object", "svg", "math", "template"):
            self.suppressed.append(tag)
            return
        if tag not in TAGS:
            return
        attrs = dict(attrs)
        if tag == "span" and attrs.get("data-wathiq-link"):
            tag = "a"
            attrs = {"href": "wathiq-resource:" + attrs["data-wathiq-link"]}
        if tag == "a" and (attrs.get("href") or "").startswith("wathiq-resource:"):
            try:
                token = str(UUID(attrs["href"].split(":", 1)[1]))
            except ValueError:
                invalid("message_resource_token_invalid")
            self.tokens.append(token)
            self.output.append(f'<span data-wathiq-link="{token}"></span>')
            self.suppressed.append(
                "span" if self.get_starttag_text().lower().startswith("<span") else tag
            )  # Never store client-provided target labels.
            return
        attribute = ""
        if tag == "a":
            href = attrs.get("href") or ""
            parsed = urlsplit(href)
            if (
                INTERNAL_PATH.search(unquote(parsed.path).replace("\\", "/"))
                or INTERNAL_PATH.search(unquote(parsed.fragment))
                or parsed.scheme not in ("http", "https", "mailto")
            ):
                invalid("message_link_invalid")
            if any(ord(char) < 32 for char in href):
                invalid("message_link_invalid")
            attribute = f' href="{escape(href, quote=True)}" rel="noopener noreferrer"'
        self.output.append("<" + tag + attribute + ">")
        if tag != "br":
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag in self.suppressed:
                index = len(self.suppressed) - 1 - self.suppressed[::-1].index(tag)
                del self.suppressed[index:]
            return
        if tag in self.stack:
            while self.stack:
                current = self.stack.pop()
                self.output.append("</" + current + ">")
                if current == tag:
                    break

    def handle_data(self, data):
        if not self.suppressed:
            self.output.append(escape(data, quote=False))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def body(value: str, expected_tokens: list[str]) -> str:
    if len(value.encode("utf-8")) > REQUEST_BODY_BYTES:
        invalid("message_request_too_large", 413)
    parser = Sanitizer()
    try:
        parser.feed(value)
        parser.close()
    except ValueError:
        invalid("message_link_invalid")
    while parser.stack:
        parser.output.append("</" + parser.stack.pop() + ">")
    if sorted(parser.tokens) != sorted(expected_tokens) or len(
        set(parser.tokens)
    ) != len(parser.tokens):
        invalid("message_resource_tokens_mismatch")
    result = "".join(parser.output)
    if len(result.encode("utf-8")) > BODY_BYTES:
        invalid("message_body_too_large")
    return result

CAPTURE_ERROR_KEYS = {'message_capture_medium_fixed_digital': 'messaging.capture.error.message_capture_medium_fixed_digital', 'message_capture_required': 'messaging.capture.error.message_capture_required', 'message_capture_integrity': 'messaging.capture.error.message_capture_integrity', 'message_capture_chain_limit': 'messaging.capture.error.message_capture_chain_limit', 'message_capture_kind_ineligible': 'messaging.capture.error.message_capture_kind_ineligible', 'message_capture_components_fixed': 'messaging.capture.error.message_capture_components_fixed', 'message_capture_security_floor': 'messaging.capture.error.message_capture_security_floor', 'message_capture_digital_required': 'messaging.capture.error.message_capture_digital_required', 'message_capture_pdf_limit': 'messaging.capture.error.message_capture_pdf_limit', 'message_capture_render_failed': 'messaging.capture.error.message_capture_render_failed', 'message_capture_renderer_unavailable': 'messaging.capture.error.message_capture_renderer_unavailable', 'message_capture_validator_unavailable': 'messaging.capture.error.message_capture_validator_unavailable', 'message_capture_pdf_nonconforming': 'messaging.capture.error.message_capture_pdf_nonconforming'}
MESSAGING_MESSAGE_KEYS = ('messaging.capture.error.message_capture_required', 'messaging.capture.error.message_capture_integrity', 'messaging.capture.error.message_capture_chain_limit', 'messaging.capture.error.message_capture_kind_ineligible', 'messaging.capture.error.message_capture_components_fixed', 'messaging.capture.error.message_capture_security_floor', 'messaging.capture.error.message_capture_digital_required', 'messaging.capture.error.message_capture_pdf_limit', 'messaging.capture.error.message_capture_render_failed', 'messaging.capture.error.message_capture_renderer_unavailable', 'messaging.capture.error.message_capture_validator_unavailable', 'messaging.capture.error.message_capture_pdf_nonconforming')
