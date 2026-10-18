"""Free text from OpenProject reaches the agent inside the untrusted-content delimiter.

A description, a comment or a help text is written by users of the instance, and an agent that
reads it must be able to tell it from instructions. An adapter that extracts such text has to pass
it through `delimit_user_content`; the few extractions that are not user text are listed.
"""

from __future__ import annotations

import ast
from pathlib import Path

ADAPTERS = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp" / "app" / "adapters"

EXTRACTORS = {"_extract_formattable_text_with_meta", "extract_formattable_text_with_meta", "_extract_formattable_text"}
DELIMITERS = {"_delimit_user_content", "delimit_user_content"}

# (file, function) -> why this extraction is not text a user wrote
NOT_USER_TEXT: dict[tuple[str, str], str] = {
    ("httpx_attachment_api.py", "_extract_formattable_text"): "returns the text; normalize_attachment delimits it",
}


def _called(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        return func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return None


def _delimited_names(function: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        if _called(node) in DELIMITERS and isinstance(node, ast.Call):
            for argument in node.args:
                names.update(n.id for n in ast.walk(argument) if isinstance(n, ast.Name))
    return names


def _first_target(assign: ast.Assign) -> str | None:
    target = assign.targets[0]
    if isinstance(target, ast.Tuple) and target.elts and isinstance(target.elts[0], ast.Name):
        return target.elts[0].id
    return target.id if isinstance(target, ast.Name) else None


def _violations() -> tuple[list[str], int]:
    problems: list[str] = []
    checked = 0
    for path in sorted(ADAPTERS.glob("httpx_*.py")):
        for function in ast.walk(ast.parse(path.read_text())):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            delimited = _delimited_names(function)
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and _called(node.value) in EXTRACTORS:
                    checked += 1
                    name = _first_target(node)
                    if name not in delimited and (path.name, function.name) not in NOT_USER_TEXT:
                        problems.append(f"{path.name}:{node.lineno} {function.name} extracts text into {name!r}")
                if _called(node) == "get" and isinstance(node, ast.Call):
                    first = node.args[0] if node.args else None
                    if isinstance(first, ast.Constant) and first.value == "raw":
                        checked += 1
                        if not delimited and (path.name, function.name) not in NOT_USER_TEXT:
                            problems.append(f"{path.name}:{node.lineno} {function.name} reads a raw text field")
    return problems, checked


def test_every_text_an_adapter_extracts_is_delimited_or_listed() -> None:
    problems, checked = _violations()

    assert checked >= 15, "the scan found too few text extractions to be reading the adapters"
    assert problems == [], "pass the text through delimit_user_content or list it in NOT_USER_TEXT with the reason"


def test_the_scan_catches_a_text_that_is_not_delimited() -> None:
    function = ast.parse(
        "def f(payload):\n    text, cut, size = _extract_formattable_text_with_meta(payload.get('x'), limit=1)\n    return text\n"
    ).body[0]
    delimiting = ast.parse(
        "def f(payload):\n    text, cut, size = _extract_formattable_text_with_meta(payload.get('x'), limit=1)\n    return _delimit_user_content(text)\n"
    ).body[0]

    assert _delimited_names(function) == set()
    assert _delimited_names(delimiting) == {"text"}
