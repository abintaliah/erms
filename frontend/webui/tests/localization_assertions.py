"""Helpers for source-structure tests after UI message localization."""
from __future__ import annotations

import json
import re
import ast
from functools import lru_cache

from frontend.webui.i18n_catalogue import load_english_manifest


_CALL = re.compile(r'render_message\("([^"]+)"\)')


@lru_cache(maxsize=8)
def with_english_messages(source: str) -> str:
    """Resolve catalogue calls to English for assertions about surrounding UI structure."""
    manifest = load_english_manifest()
    source = _CALL.sub(
        lambda match: json.dumps(
            manifest[match.group(1)]["default_text"], ensure_ascii=False,
        ),
        source,
    )
    tree = ast.parse(source)
    line_offsets = [0]
    for match in re.finditer("\n", source):
        line_offsets.append(match.end())

    def offset(line: int, column: int) -> int:
        start = line_offsets[line - 1]
        raw = source[start:].split("\n", 1)[0]
        return start + len(raw.encode("utf-8")[:column].decode("utf-8"))

    replacements = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "render_message"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        definition = manifest[node.args[0].value]
        rendered = definition["default_text"]
        dynamic = False
        for keyword in node.keywords:
            marker = "{" + str(keyword.arg) + "}"
            expression = source[
                offset(keyword.value.lineno, keyword.value.col_offset):
                offset(keyword.value.end_lineno, keyword.value.end_col_offset)
            ] or "None"
            if marker in rendered:
                rendered = rendered.replace(marker, "{" + expression + "}")
                dynamic = True
        replacement = ("f" if dynamic else "") + json.dumps(rendered, ensure_ascii=False)
        replacements.append((
            offset(node.lineno, node.col_offset),
            offset(node.end_lineno, node.end_col_offset),
            replacement,
        ))
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source
