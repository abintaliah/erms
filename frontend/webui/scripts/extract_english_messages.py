#!/usr/bin/env python3
"""Inventory untranslated WebUI text as input to contextual catalogue conversion.

This deliberately covers more than literal arguments.  Visible text is often built
with f-strings, assigned to ``component.text`` after construction, or stored in a
local variable before it reaches a UI component.  The report preserves the source
expression and marks dynamic candidates for human/agent review.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path


WEBUI_DIR = Path(__file__).resolve().parents[1]
VISIBLE_CALLS = {
    "button", "label", "link", "input", "textarea", "select", "checkbox",
    "number", "radio", "tab", "tooltip", "notification", "notify", "dialog", "card",
    "expansion", "badge", "code", "menu_item",
}
VISIBLE_KEYWORDS = {"text", "label", "placeholder", "message", "caption"}
VISIBLE_ATTRIBUTES = {"text", "label", "placeholder", "message", "caption"}
WORDS = re.compile(r"[A-Za-z]{2,}")


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _scope(parents: list[ast.AST]) -> str:
    for parent in reversed(parents):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return parent.name
    return "module"


def _english_fragments(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) and WORDS.search(node.value) else []
    if isinstance(node, ast.JoinedStr):
        return [
            value.value for value in node.values
            if isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and WORDS.search(value.value)
        ]
    if isinstance(node, ast.IfExp):
        return _english_fragments(node.body) + _english_fragments(node.orelse)
    if isinstance(node, ast.Subscript):
        # Visible labels and placeholders are commonly selected from an inline
        # mapping (for example, per-resource filters).  The previous audit
        # stopped at the subscript and silently missed every value in the map.
        return _english_fragments(node.value)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            return _english_fragments(node.func.value) + [
                fragment
                for argument in node.args[1:]
                for fragment in _english_fragments(argument)
            ]
        return []
    if isinstance(node, ast.Dict):
        return [fragment for value in node.values for fragment in _english_fragments(value)]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.BoolOp, ast.BinOp)):
        children = (
            node.elts if isinstance(node, (ast.List, ast.Tuple, ast.Set))
            else node.values if isinstance(node, ast.BoolOp)
            else (node.left, node.right)
        )
        return [fragment for child in children for fragment in _english_fragments(child)]
    return []


def _is_localized(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call) and _call_name(child) in {"render_message", "gettext", "translate"}
        for child in ast.walk(node)
    )


def extract(root: Path = WEBUI_DIR) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".venv", "tests", "scripts", "__pycache__"} for part in path.parts):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        parents: list[ast.AST] = []
        seen: set[tuple[int, int, str]] = set()
        assigned_text: dict[str, ast.AST] = {}

        def record(node: ast.AST, component: str, kind: str) -> None:
            if isinstance(node, ast.Name) and node.id in assigned_text:
                node = assigned_text[node.id]
            if _is_localized(node):
                return
            fragments = _english_fragments(node)
            if not fragments:
                return
            identity = (
                getattr(node, "lineno", 0), getattr(node, "col_offset", 0), component,
            )
            if identity in seen:
                return
            seen.add(identity)
            scope = _scope(parents)
            relative = path.relative_to(root).as_posix()
            expression = ast.unparse(node)
            results.append({
                "source_text": " ".join(fragments),
                "source_expression": expression,
                "source_file": relative,
                "source_line": getattr(node, "lineno", 0),
                "component": component,
                "candidate_kind": kind,
                "dynamic": not isinstance(node, ast.Constant),
                "code_context": scope,
                "suggested_contextual_key": f"{scope.strip('_').lower()}.{component}.needs_naming",
            })

        class Visitor(ast.NodeVisitor):
            def generic_visit(self, node: ast.AST) -> None:
                parents.append(node)
                super().generic_visit(node)
                parents.pop()

            def visit_Call(self, node: ast.Call) -> None:
                call = _call_name(node)
                # NiceGUI visible text is the first positional argument; later
                # positional arguments are callbacks, values, icons, or options.
                values = list(node.args[:1]) + [
                    item.value for item in node.keywords if item.arg in VISIBLE_KEYWORDS
                ]
                if call in VISIBLE_CALLS:
                    for value in values:
                        record(value, call, "ui_call")
                elif call == "props" and node.args:
                    value = node.args[0]
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and re.search(r"(?:aria-label|title)=['\"][^'\"]*[A-Za-z]", value.value)
                    ):
                        record(value, "accessible_name", "component_props")
                self.generic_visit(node)

            def visit_Assign(self, node: ast.Assign) -> None:
                for target in node.targets:
                    if isinstance(target, ast.Name) and _english_fragments(node.value):
                        assigned_text[target.id] = node.value
                        if target.id.endswith(("_options", "_by_resource", "_facts", "_HELP")):
                            record(node.value, target.id, "presentation_data")
                    if isinstance(target, ast.Attribute) and target.attr in VISIBLE_ATTRIBUTES:
                        record(node.value, target.attr, "component_assignment")
                self.generic_visit(node)

            def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
                if (
                    node.value is not None
                    and isinstance(node.target, ast.Attribute)
                    and node.target.attr in VISIBLE_ATTRIBUTES
                ):
                    record(node.value, node.target.attr, "component_assignment")
                self.generic_visit(node)

        Visitor().visit(tree)
    return results


if __name__ == "__main__":
    print(json.dumps(extract(), ensure_ascii=False, indent=2))
