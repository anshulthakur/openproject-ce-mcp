"""Text sent to a server-side LIKE filter is escaped where OpenProject does not escape it.

OpenProject 16.0 to 17.9 put the value of the project and user name filters into
`LIKE '%value%'` unescaped, so `_` and `%` typed by a user act as wildcards. Other text filters
(work package subjects, custom fields) are escaped by OpenProject itself, and escaping them here
would escape twice. A filter literal that uses a text operator must say which of the two it is.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp"

TEXT_OPERATORS = {"~", "!~", "**"}

# filter key -> True when OpenProject puts the value into LIKE unescaped, so the caller must
RAW_LIKE = {"name": True, "name_and_identifier": True, "subject_or_id": False, "title": False}


def _constant(node: ast.expr | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _text_filters() -> list[tuple[str, int, str, ast.expr | None]]:
    """(file, line, filter key, first value expression) of every `{key: {"operator": <text>, "values": [...]}}`."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if not isinstance(value, ast.Dict):
                    continue
                fields = {_constant(k): v for k, v in zip(value.keys, value.values, strict=True)}
                if _constant(fields.get("operator")) not in TEXT_OPERATORS:
                    continue
                values = fields.get("values")
                first = values.elts[0] if isinstance(values, ast.List) and values.elts else None
                found.append((path.name, node.lineno, str(_constant(key)), first))
    return found


def _is_escaped(expression: ast.expr | None) -> bool:
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "escape_like"
    )


def test_every_text_filter_is_classified() -> None:
    filters = _text_filters()

    assert len(filters) >= 3, "the scan found too few text filters to be reading the source"
    unclassified = [f"{name}:{line} filter {key!r}" for name, line, key, _ in filters if key not in RAW_LIKE]
    assert unclassified == [], "add the filter key to RAW_LIKE: True if OpenProject does not escape its value"


def test_a_filter_that_openproject_does_not_escape_gets_escaped_text() -> None:
    unescaped = [
        f"{name}:{line} filter {key!r}"
        for name, line, key, first in _text_filters()
        if RAW_LIKE.get(key) and not _is_escaped(first)
    ]

    assert unescaped == []


def test_a_filter_that_openproject_escapes_is_not_escaped_twice() -> None:
    doubled = [
        f"{name}:{line} filter {key!r}"
        for name, line, key, first in _text_filters()
        if RAW_LIKE.get(key) is False and _is_escaped(first)
    ]

    assert doubled == []


def test_the_scan_reads_a_filter_literal() -> None:
    tree = ast.parse('{"name": {"operator": "~", "values": [escape_like(text)]}}')
    assert isinstance(tree.body[0], ast.Expr)
    literal = tree.body[0].value
    assert isinstance(literal, ast.Dict)
    inner = literal.values[0]
    assert isinstance(inner, ast.Dict)
    assert _constant(inner.keys[0]) == "operator" and _constant(inner.values[0]) in TEXT_OPERATORS
