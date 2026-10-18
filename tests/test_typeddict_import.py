"""pydantic builds a schema from `typing_extensions.TypedDict` only before Python 3.12.

`typing.TypedDict` works on the Python the developer runs and fails at server start on 3.11, which the
package supports; so the source takes it from `typing_extensions`.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp"


def _imports_typing_typeddict(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "typing":
            if any(alias.name == "TypedDict" for alias in node.names):
                return True
        # `import typing` and `typing.TypedDict`, also under another name
        if isinstance(node, ast.Attribute) and node.attr == "TypedDict":
            if isinstance(node.value, ast.Name) and node.value.id in {"typing", "t"}:
                return True
    return False


def test_no_module_takes_typeddict_from_typing() -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in sorted(SOURCE.rglob("*.py"))
        if _imports_typing_typeddict(ast.parse(path.read_text()))
    ]

    assert offenders == []


def test_the_check_sees_the_forbidden_import() -> None:
    assert _imports_typing_typeddict(ast.parse("from typing import Any, TypedDict"))
    assert _imports_typing_typeddict(ast.parse("import typing\n\nclass A(typing.TypedDict): ..."))
    assert not _imports_typing_typeddict(ast.parse("from typing_extensions import TypedDict"))
