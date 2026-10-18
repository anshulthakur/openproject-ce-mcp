"""AST walk shared by the tests that audit what the adapters, services and integration tests do."""

from __future__ import annotations

import ast
from collections.abc import Callable, Collection
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp" / "app"
ADAPTERS = APP / "adapters"
SERVICES = APP / "services"
INTEGRATION = Path(__file__).resolve().parent / "integration"


def matching_nodes(
    predicate: Callable[[ast.AST], bool],
    *,
    directories: Collection[Path] = (ADAPTERS,),
    source: str | None = None,
) -> dict[str, list[ast.AST]]:
    """`file:function` -> the nodes inside that function for which `predicate` holds.
    Scans the given directories, or the given source text when a test plants one."""
    sources = (
        {"planted.py": source}
        if source is not None
        else {p.name: p.read_text() for directory in directories for p in sorted(directory.glob("*.py"))}
    )
    found: dict[str, list[ast.AST]] = {}
    for name, text in sources.items():
        for function in ast.walk(ast.parse(text)):
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes = [node for node in ast.walk(function) if predicate(node)]
                if nodes:
                    found.setdefault(f"{name}:{function.name}", []).extend(nodes)
    return found


def calls_named(name: str) -> Callable[[ast.AST], bool]:
    return lambda node: isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name


def reads_key(keys: Collection[str]) -> Callable[[ast.AST], bool]:
    """`.get("key")` or `["key"]` with a constant key among `keys`."""

    def predicate(node: ast.AST) -> bool:
        key = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            key = node.args[0] if node.args else None
        elif isinstance(node, ast.Subscript):
            key = node.slice
        return isinstance(key, ast.Constant) and key.value in keys

    return predicate


def constant_key_reads(
    keys: Collection[str], *, directories: Collection[Path] = (ADAPTERS,), source: str | None = None
) -> dict[str, int]:
    """`file:function` -> first line of every function that reads one of `keys`."""
    nodes = matching_nodes(reads_key(keys), directories=directories, source=source)
    return {name: found[0].lineno for name, found in nodes.items()}  # type: ignore[attr-defined]
