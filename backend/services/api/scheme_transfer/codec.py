"""Pure interchange codecs. No database, authentication or UI dependencies."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker

MAX_BYTES = 32 * 1024 * 1024
MAX_CLASSES = 10000
csv.field_size_limit(MAX_BYTES)
COLUMNS = "format_version,row_type,scheme_code,classification_code,parent_code,source_id,field_name,language_tag,value,value_state".split(
    ","
)
FIELDS = {
    "scheme": "title description authority scope_note edition date_created date_updated date_published date_deactivated date_first_used version translations".split(),
    "classification": "title description authority scope_note keywords is_terminal date_created date_updated date_deactivated date_first_used version translations has_retention_rule".split(),
    "retention_rule": "current_period_years intermediate_period_years final_disposition instructions date_created date_updated version".split(),
}
MANIFEST = {
    "export_id": ("export_id",),
    "exported_at": ("exported_at",),
    **{
        f"exported_by_{k}": ("exported_by", k)
        for k in ("source_user_id", "username", "display_name")
    },
    **{
        f"source_{k}": ("source", k)
        for k in (
            "application",
            "application_revision",
            "database_name",
            "schema_version",
        )
    },
    "classification_count": ("counts", "classifications"),
    "retention_rule_count": ("counts", "retention_rules"),
    **{
        f"checksum_{k}": ("checksum", k)
        for k in ("algorithm", "canonicalization", "scope", "encoding", "value")
    },
}


class TransferError(ValueError):
    """Safe validation failure; callers localize the message code."""

    def __init__(self, code: str, field: str = ""):
        self.code, self.field = code, field
        super().__init__(f"{code}: {field}")


def fail(field: str, code: str = "invalid_package"):
    raise TransferError(code, field)


@lru_cache(maxsize=1)
def validator():
    schema = json.loads(Path(__file__).with_name("v1.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


def ordered(classes: list[dict]) -> list[dict]:
    """Iterative traversal: hierarchy depth does not consume Python call frames."""
    by_code, children = {}, {}
    for item in classes:
        code = item["code"]
        if code in by_code:
            fail(code, "duplicate_code")
        by_code[code] = item
        children.setdefault(item["parent_code"], []).append(item)
    for item in classes:
        parent = item["parent_code"]
        if parent is not None and (
            parent not in by_code or by_code[parent]["is_terminal"]
        ):
            fail(item["code"], "invalid_hierarchy")
    for branch in children.values():
        branch.sort(key=lambda c: c["code"].encode("utf-8"))
    stack, result = list(reversed(children.get(None, []))), []
    while stack:
        item = stack.pop()
        result.append(item)
        stack.extend(reversed(children.get(item["code"], [])))
    if len(result) != len(classes):
        fail("parent_code", "invalid_hierarchy")
    return result


def validate(package: dict, *, checksum: bool = True) -> dict:
    error = next(validator().iter_errors(package), None)
    if error:
        fail(".".join(map(str, error.absolute_path)))
    scheme = package["data"]["scheme"]
    classes = scheme["classifications"]
    counts = package["manifest"]["counts"]
    if counts != {
        "classifications": len(classes),
        "retention_rules": sum(c["retention_rule"] is not None for c in classes),
    }:
        fail("counts")
    effective = {}
    source_ids, rule_ids = set(), set()
    for item in ordered(classes):
        if item["source_id"] in source_ids:
            fail(item["code"], "duplicate_source_id")
        source_ids.add(item["source_id"])
        rule = item["retention_rule"]
        if rule:
            if rule["source_id"] in rule_ids:
                fail(item["code"], "duplicate_source_id")
            rule_ids.add(rule["source_id"])
        effective[item["code"]] = rule or effective.get(item["parent_code"])
        if item["is_terminal"] and not effective[item["code"]]:
            fail(item["code"], "missing_retention_rule")
    entities = [
        scheme,
        *classes,
        *(c["retention_rule"] for c in classes if c["retention_rule"]),
    ]
    now = datetime.now(timezone.utc)
    for entity in entities:
        for key in ("source_id", "version"):
            if int(entity[key]) > 9223372036854775807:
                fail(key)
        created = datetime.fromisoformat(entity["date_created"])
        for key in ("date_deactivated", "date_first_used"):
            if entity.get(key) is not None:
                value = datetime.fromisoformat(entity[key])
                if value < created or (key == "date_deactivated" and value > now):
                    fail(key)
    if int(package["manifest"]["exported_by"]["source_user_id"]) > 9223372036854775807:
        fail("source_user_id")
    if checksum and not hmac.compare_digest(
        package["manifest"]["checksum"]["value"], digest(package)
    ):
        fail("checksum", "checksum_mismatch")
    return package


def digest(package: dict) -> str:
    payload = dict(package)
    payload["manifest"] = {
        k: v for k, v in package["manifest"].items() if k != "checksum"
    }
    try:
        return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()
    except (ValueError, UnicodeError) as exc:
        raise TransferError("invalid_package", "canonicalization") from exc


def seal(package: dict) -> dict:
    package["manifest"]["checksum"] = dict(
        algorithm="SHA-256",
        canonicalization="RFC8785",
        scope="package_excluding_checksum",
        encoding="hex",
        value="0" * 64,
    )
    package["manifest"]["checksum"]["value"] = digest(package)
    return validate(package)


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            fail(key, "duplicate_field")
        obj[key] = value
    return obj


def decode(raw: bytes, file_format: str) -> dict:
    if len(raw) > MAX_BYTES:
        fail("file", "file_too_large")
    try:
        if file_format == "json":
            package = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_pairs,
                parse_constant=lambda _: fail("number"),
            )
        elif file_format == "csv":
            package = from_csv(raw.decode("utf-8-sig"))
        else:
            fail("format")
        return validate(package)
    except TransferError:
        raise
    except (
        ValueError,
        UnicodeError,
        RecursionError,
        csv.Error,
        KeyError,
        TypeError,
    ) as exc:
        raise TransferError("invalid_package", "file") from exc


def encode(package: dict, file_format: str) -> bytes:
    validate(package)
    result = (
        (json.dumps(package, ensure_ascii=False, indent=2) + "\n").encode()
        if file_format == "json"
        else to_csv(package)
    )
    if len(result) > MAX_BYTES:
        fail("file", "file_too_large")
    return result


def to_csv(package: dict) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    scheme = package["data"]["scheme"]

    def row(kind, owner, field, value, lang="", state=None):
        if state is None:
            state = "null" if value is None else "value"
        text = (
            ""
            if value is None
            else str(value).lower() if isinstance(value, bool) else str(value)
        )
        writer.writerow(
            [
                "1.0",
                kind,
                scheme["code"],
                owner.get("code", "") if kind != "scheme" else "",
                owner.get("parent_code") or "" if kind == "classification" else "",
                owner.get("source_id", ""),
                field,
                lang,
                text,
                state,
            ]
        )

    for field, path in MANIFEST.items():
        value = package["manifest"]
        for key in path:
            value = value[key]
        row("manifest", {}, field, value)

    def entity(kind, obj):
        for field in FIELDS[kind]:
            value = (
                bool(obj["retention_rule"])
                if field == "has_retention_rule"
                else obj[field]
            )
            if field == "translations" and value is not None:
                row(
                    kind,
                    obj,
                    field,
                    "present" if value else "",
                    state="value" if value else "empty_object",
                )
            else:
                row(kind, obj, field, value)
        for lang, values in sorted((obj.get("translations") or {}).items()):
            for field in ("title", "description"):
                if field in values:
                    owner = dict(obj, code="" if kind == "scheme" else obj["code"])
                    row("translation", owner, field, values[field], lang)

    entity("scheme", scheme)
    for item in ordered(scheme["classifications"]):
        entity("classification", item)
        if item["retention_rule"]:
            entity("retention_rule", dict(item["retention_rule"], code=item["code"]))
    return out.getvalue().encode()


def from_csv(text: str) -> dict:
    # Input is byte-bounded before parsing, including individual quoted fields.
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    if next(reader, None) != COLUMNS:
        fail("header")
    groups, translated, scheme_code = {}, [], None
    for values in reader:
        if len(values) != len(COLUMNS):
            fail("row_width")
        version, kind, code, owner, parent, source, field, lang, value, state = values
        if (
            version != "1.0"
            or not code
            or (scheme_code is not None and scheme_code != code)
        ):
            fail("scheme_code")
        scheme_code = code
        if kind not in (*FIELDS, "manifest", "translation") or state not in (
            "value",
            "null",
            "empty_object",
        ):
            fail("row_type")
        if state != "value" and value:
            fail(field)
        if kind != "classification" and parent or kind != "translation" and lang:
            fail("row_context")
        if kind in ("manifest", "scheme") and owner or kind == "manifest" and source:
            fail("owner")
        if kind in ("classification", "retention_rule") and not owner:
            fail("owner")
        if kind == "translation":
            if field not in ("title", "description") or not lang or state != "value":
                fail(field)
            translated.append((owner, source, lang, field, value))
            continue
        allowed = MANIFEST if kind == "manifest" else FIELDS[kind]
        if field not in allowed:
            fail(field)
        group = groups.setdefault(
            (kind, owner), {"source": source, "parent": parent, "values": {}}
        )
        if (source, parent) != (group["source"], group["parent"]) or field in group[
            "values"
        ]:
            fail(field, "duplicate_field")
        if state == "empty_object":
            if field != "translations":
                fail(field)
            parsed = {}
        elif state == "null":
            parsed = None
        elif field in ("is_terminal", "has_retention_rule"):
            if value not in ("true", "false"):
                fail(field)
            parsed = value == "true"
        elif field in (
            "current_period_years",
            "intermediate_period_years",
            "classification_count",
            "retention_rule_count",
        ):
            if not re.fullmatch(r"0|[1-9][0-9]*", value):
                fail(field)
            parsed = int(value)
        else:
            parsed = value
        group["values"][field] = parsed
    if not scheme_code:
        fail("scheme")
    for (kind, owner), group in groups.items():
        if set(group["values"]) != set(
            MANIFEST if kind == "manifest" else FIELDS[kind]
        ):
            fail(owner or kind, "missing_field")
    manifest_values = groups[("manifest", "")]["values"]
    manifest = {}
    for field, path in MANIFEST.items():
        target = manifest
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = manifest_values[field]

    def entity(kind, owner):
        group = groups[(kind, owner)]
        return dict(group["values"], source_id=group["source"])

    scheme = entity("scheme", "")
    scheme["code"] = scheme_code
    classes = {}
    for (kind, owner), group in groups.items():
        if kind == "classification":
            item = entity(kind, owner)
            flag = item.pop("has_retention_rule")
            if type(flag) is not bool or flag != (("retention_rule", owner) in groups):
                fail(owner, "invalid_retention_rule")
            item.update(
                code=owner,
                parent_code=group["parent"] or None,
                retention_rule=entity("retention_rule", owner) if flag else None,
            )
            classes[owner] = item
        if kind == "retention_rule" and ("classification", owner) not in groups:
            fail(owner, "invalid_retention_rule")
    entities = {"": scheme, **classes}
    for owner, source, lang, field, value in translated:
        if owner not in entities or entities[owner]["source_id"] != source:
            fail(owner, "invalid_translation")
        entity_obj = entities[owner]
        if entity_obj["translations"] == "present":
            entity_obj["translations"] = {}
        elif (
            not isinstance(entity_obj["translations"], dict)
            or groups[("classification" if owner else "scheme", owner)]["values"][
                "translations"
            ]
            != "present"
        ):
            fail(owner, "invalid_translation")
        translation = entity_obj["translations"].setdefault(lang, {})
        if field in translation:
            fail(field, "duplicate_field")
        translation[field] = value
    for obj in entities.values():
        if obj["translations"] == "present":
            fail("translations", "missing_field")
    # Validate shape before traversing untrusted relationships.
    scheme["classifications"] = list(classes.values())
    package = dict(
        package_type="classification_scheme_export",
        format_version="1.0",
        manifest=manifest,
        data={"scheme": scheme},
    )
    validate(package, checksum=False)
    scheme["classifications"] = ordered(scheme["classifications"])
    return package
