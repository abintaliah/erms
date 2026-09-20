import ast
from pathlib import Path


APP_PATH = Path(__file__).parents[1] / "app.py"


def test_security_administration_pages_can_be_restored_from_navigation_history():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    restore = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "restore_navigation_entry"
    )
    recognized_pages = {
        comparison.value
        for node in ast.walk(restore)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "page"
        for comparison in node.comparators
        if isinstance(comparison, ast.Constant) and isinstance(comparison.value, str)
    }
    assert {"governance-custody", "security-operations"} <= recognized_pages
