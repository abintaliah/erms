#!/usr/bin/env python3
"""Convert legacy literal NiceGUI messages to contextual catalogue keys.

This migration is deterministic and source preserving: it edits only the
literal AST spans identified by ``extract_english_messages`` and merges the
corresponding definitions into the authoritative English manifest.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path


WEBUI_DIR = Path(__file__).resolve().parents[1]
APP = WEBUI_DIR / "app.py"
MANIFEST = WEBUI_DIR / "i18n" / "messages.en.json"
VISIBLE_CALLS = {
    "button", "label", "link", "input", "textarea", "select", "checkbox",
    "number", "radio", "tab", "tooltip", "notification", "notify", "dialog", "card",
    "expansion", "badge", "code", "menu_item",
}
VISIBLE_ATTRIBUTES = {"text", "label", "placeholder", "message", "caption"}
WORDS = re.compile(r"[A-Za-z]{2,}")


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value[:42].rstrip("_") or "message"


def placeholder_base(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return re.sub(r"[^a-z0-9_]+", "_", str(node.slice.value).lower()).strip("_") or "value"
    if isinstance(node, ast.Call):
        name = call_name(node)
        if name == "len" and node.args:
            subject = placeholder_base(node.args[0])
            return subject.removesuffix("s") + "_count"
        return name or "value"
    return "value"


def main() -> None:
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP))
    parents: list[ast.AST] = []
    replacements: list[tuple[int, int, str]] = []
    definitions: dict[str, dict[str, object]] = {}
    visible_names: set[str] = set()
    line_offsets = [0]
    for match in re.finditer("\n", source):
        line_offsets.append(match.end())

    def offset(line: int, column: int) -> int:
        # AST columns are UTF-8 byte offsets. Decode the prefix to obtain the
        # character offset used by Python string slicing.
        line_start = line_offsets[line - 1]
        raw_line = source[line_start:].split("\n", 1)[0]
        prefix = raw_line.encode("utf-8")[:column].decode("utf-8")
        return line_start + len(prefix)

    def scope() -> str:
        for parent in reversed(parents):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                return parent.name.strip("_").lower() or "module"
        return "module"

    for candidate in ast.walk(tree):
        if isinstance(candidate, ast.Call) and call_name(candidate) in VISIBLE_CALLS:
            values = list(candidate.args[:1]) + [
                item.value for item in candidate.keywords
                if item.arg in {"text", "label", "placeholder", "message"}
            ]
            visible_names.update(
                value.id for value in values if isinstance(value, ast.Name)
            )
        elif isinstance(candidate, ast.Assign):
            if any(
                isinstance(target, ast.Attribute) and target.attr in VISIBLE_ATTRIBUTES
                for target in candidate.targets
            ) and isinstance(candidate.value, ast.Name):
                visible_names.add(candidate.value.id)

    class Visitor(ast.NodeVisitor):
        def generic_visit(self, node: ast.AST) -> None:
            parents.append(node)
            super().generic_visit(node)
            parents.pop()

        def collect_static(self, value: ast.AST, component: str) -> None:
            if isinstance(value, ast.Constant):
                if isinstance(value.value, str) and WORDS.search(value.value):
                    self.add_literal(value, component)
                return
            if isinstance(value, ast.IfExp):
                self.collect_static(value.body, component)
                self.collect_static(value.orelse, component)
                return
            if isinstance(value, ast.Subscript):
                self.collect_static(value.value, component)
                return
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "get"
            ):
                self.collect_static(value.func.value, component)
                if len(value.args) > 1:
                    self.collect_static(value.args[1], component)
                return
            if isinstance(value, ast.BoolOp):
                for child in value.values:
                    self.collect_static(child, component)
                return
            if isinstance(value, ast.Dict):
                for child in value.values:
                    self.collect_static(child, component)
                return
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                for child in value.elts:
                    self.collect_static(child, component)

        def collect_dynamic(self, value: ast.AST, component: str) -> None:
            if isinstance(value, ast.JoinedStr):
                self.add_template(value, component)
                return
            if isinstance(value, ast.IfExp):
                self.collect_dynamic(value.body, component)
                self.collect_dynamic(value.orelse, component)
                return
            if isinstance(value, ast.Subscript):
                self.collect_dynamic(value.value, component)
                return
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "get"
            ):
                self.collect_dynamic(value.func.value, component)
                if len(value.args) > 1:
                    self.collect_dynamic(value.args[1], component)
                return
            if isinstance(value, ast.BoolOp):
                for child in value.values:
                    self.collect_dynamic(child, component)
                return
            if isinstance(value, ast.Dict):
                for child in value.values:
                    self.collect_dynamic(child, component)
                return
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                for child in value.elts:
                    self.collect_dynamic(child, component)

        def add_template(self, value: ast.JoinedStr, component: str) -> None:
            context = scope()
            template_parts: list[str] = []
            parameters: list[tuple[str, str]] = []
            used: dict[str, int] = {}
            expression_names: dict[str, str] = {}
            for part in value.values:
                if isinstance(part, ast.Constant):
                    template_parts.append(str(part.value).replace("{", "{{").replace("}", "}}"))
                    continue
                if not isinstance(part, ast.FormattedValue):
                    continue
                expression = ast.unparse(part.value)
                if expression in expression_names:
                    name = expression_names[expression]
                else:
                    base = re.sub(r"[^a-z0-9_]+", "_", placeholder_base(part.value).lower()).strip("_") or "value"
                    used[base] = used.get(base, 0) + 1
                    name = base if used[base] == 1 else f"{base}_{used[base]}"
                    expression_names[expression] = name
                    argument = expression
                    if part.format_spec is not None:
                        spec = "".join(
                            str(item.value) for item in part.format_spec.values
                            if isinstance(item, ast.Constant)
                        )
                        argument = f"format({expression}, {spec!r})"
                    parameters.append((name, argument))
                template_parts.append("{" + name + "}")
            template = "".join(template_parts)
            if not WORDS.search(template):
                return
            digest = hashlib.sha1(
                f"{context}\0{component}\0{template}".encode()
            ).hexdigest()[:8]
            key = f"webui.{context}.{component}.{slug(template)}_{digest}"
            arguments = "".join(f", {name}={expression}" for name, expression in parameters)
            start = offset(value.lineno, value.col_offset)
            end = offset(value.end_lineno, value.end_col_offset)
            replacements.append((start, end, f'render_message("{key}"{arguments})'))
            role = "notification message" if component == "notify" else "interface text"
            schema = {name: "text" for name, _ in parameters}
            example = template
            for name, _ in parameters:
                example = example.replace("{" + name + "}", f"<{name}>")
            definitions[key] = {
                "context_group": f"webui.{context}",
                "default_text": template,
                "semantic_meaning": f"Interpolated {role} in the {context.replace('_', ' ')} workflow.",
                "common_locations": [f"WebUI: {context.replace('_', ' ')}"],
                "translator_guidance": "Translate the complete message naturally and preserve every named placeholder exactly.",
                "grammatical_role": role,
                "parameter_schema": schema,
                "rendered_example": example,
                "is_html": False,
            }

        def add_accessible_prop(self, value: ast.Constant) -> None:
            raw = str(value.value)
            match = re.search(r"(?:aria-label|title)=(['\"])([^'\"]*[A-Za-z][^'\"]*)\1", raw)
            if not match:
                return
            visible = match.group(2)
            context = scope()
            digest = hashlib.sha1(
                f"{context}\0accessible_name\0{visible}".encode()
            ).hexdigest()[:8]
            key = f"webui.{context}.accessible_name.{slug(visible)}_{digest}"
            before = raw[:match.start(2)]
            after = raw[match.end(2):]
            replacement = f"{before!r} + render_message(\"{key}\") + {after!r}"
            start = offset(value.lineno, value.col_offset)
            end = offset(value.end_lineno, value.end_col_offset)
            replacements.append((start, end, replacement))
            definitions[key] = {
                "context_group": f"webui.{context}",
                "default_text": visible,
                "semantic_meaning": f"Accessible name in the {context.replace('_', ' ')} workflow.",
                "common_locations": [f"WebUI accessibility: {context.replace('_', ' ')}"],
                "translator_guidance": "Translate as a concise accessible name for the corresponding control or region.",
                "grammatical_role": "accessible name",
                "parameter_schema": {},
                "rendered_example": visible,
                "is_html": False,
            }

        def add_literal(self, value: ast.Constant, component: str) -> None:
            context = scope()
            digest = hashlib.sha1(
                f"{context}\0{component}\0{value.value}".encode()
            ).hexdigest()[:8]
            key = f"webui.{context}.{component}.{slug(value.value)}_{digest}"
            start = offset(value.lineno, value.col_offset)
            end = offset(value.end_lineno, value.end_col_offset)
            replacements.append((start, end, f'render_message("{key}")'))
            role = {
                "button": "action label", "tooltip": "action guidance",
                "notify": "notification message", "input": "field label",
                "textarea": "field label", "select": "field or option label",
                "checkbox": "option label", "tab": "navigation label",
                "label": "interface text", "text": "interface text",
            }.get(component, "interface text")
            definitions[key] = {
                "context_group": f"webui.{context}",
                "default_text": value.value,
                "semantic_meaning": f"{role.capitalize()} in the {context.replace('_', ' ')} workflow.",
                "common_locations": [f"WebUI: {context.replace('_', ' ')}"],
                "translator_guidance": f"Translate as a concise {role}; preserve the intent used in this workflow.",
                "grammatical_role": role,
                "parameter_schema": {},
                "rendered_example": value.value,
                "is_html": False,
            }

        def visit_Call(self, node: ast.Call) -> None:
            component = call_name(node)
            values = list(node.args[:1]) + [
                item.value for item in node.keywords
                if item.arg in {"text", "label", "placeholder", "message"}
            ]
            if component in VISIBLE_CALLS:
                for value in values:
                    self.collect_static(value, component)
                    self.collect_dynamic(value, component)
            elif (
                component == "props" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                self.add_accessible_prop(node.args[0])
            self.generic_visit(node)

        def visit_Assign(self, node: ast.Assign) -> None:
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in VISIBLE_ATTRIBUTES:
                    self.collect_static(node.value, target.attr)
                    self.collect_dynamic(node.value, target.attr)
                elif isinstance(target, ast.Name) and target.id in visible_names:
                    self.collect_static(node.value, "text")
                    self.collect_dynamic(node.value, "text")
                elif isinstance(target, ast.Name) and target.id.endswith(
                    ("_options", "_by_resource", "_facts", "_HELP")
                ):
                    # Presentation strings kept in option maps, fact tuples,
                    # and metric definitions are just as user-visible as a
                    # literal passed directly to ui.label.
                    self.collect_static(node.value, "text")
                    self.collect_dynamic(node.value, "text")
            self.generic_visit(node)

    Visitor().visit(tree)
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    APP.write_text(source, encoding="utf-8")

    manifest_rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest = {row["message_key"]: row for row in manifest_rows}
    definitions = {
        key: {"message_key": key, **definition}
        for key, definition in definitions.items()
    }
    manifest.update(definitions)
    MANIFEST.write_text(
        json.dumps([manifest[key] for key in sorted(manifest)], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Converted {len(replacements)} literal occurrences into {len(definitions)} contextual keys.")


if __name__ == "__main__":
    main()
