"""Static check: every tool validates ``select`` before its first request.

``_validate_select``'s error tells the caller that no request was sent, which
is only true while nothing that suspends (``await``, ``async for``, ``async
with``: the only ways a tool body reaches the client) runs ahead of it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "openproject_ce_mcp"
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_SUSPENDS = (ast.Await, ast.AsyncFor, ast.AsyncWith)


def _tool_modules() -> list[Path]:
    return sorted(SRC.glob("tools_*.py"))


def _is_select_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_validate_select"


def _own_nodes(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.AST]:
    # A nested function's awaits run when it is called, not where it is defined.
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _FUNCTIONS):
            stack.extend(ast.iter_child_nodes(node))


def _position(node: ast.AST) -> tuple[int, int]:
    return (node.lineno, node.col_offset)  # type: ignore[attr-defined]


def _checked_functions(tree: ast.AST) -> Iterator[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.AST]]]:
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            yield fn, list(_own_nodes(fn))


def test_every_select_validation_runs_before_any_await() -> None:
    violations: list[str] = []
    for path in _tool_modules():
        for fn, nodes in _checked_functions(ast.parse(path.read_text(), filename=str(path))):
            awaits = [n for n in nodes if isinstance(n, _SUSPENDS)]
            for call in (n for n in nodes if _is_select_call(n)):
                violations.extend(
                    f"{path.name}:{fn.name}: await on line {a.lineno} runs before _validate_select on line {call.lineno}"
                    for a in awaits
                    if _position(a) < _position(call)
                )
    assert violations == []


def test_every_select_validation_call_is_inside_a_checked_function() -> None:
    # Guards the check above against passing vacuously, e.g. on a call it
    # never visits.
    checked = 0
    total = 0
    for path in _tool_modules():
        tree = ast.parse(path.read_text(), filename=str(path))
        total += sum(1 for n in ast.walk(tree) if _is_select_call(n))
        checked += sum(1 for _, nodes in _checked_functions(tree) for n in nodes if _is_select_call(n))
    assert total > 0
    assert checked == total
