"""A name given by a caller is never resolved to the first of several matches.

User and group names, versions, sprints, roles and custom field options can share a title, so a
function that compares two case-folded names must also refuse more than one match. The few
resources whose names OpenProject keeps unique are listed with the reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp" / "app"

# function -> why a single match is certain
UNIQUE_BY_OPENPROJECT = {
    "resolve_status_id": "status names are unique",
    "resolve_priority_id": "priority names are unique per enumeration",
    "_resolve_status_href": "the project status values are a fixed set",
    "_title_matches": "only collects; resolve_schema_option_href and the custom field option resolver refuse several",
}


def _is_casefold(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "casefold"


def _casefolded_names(function: ast.AST) -> set[str]:
    """Local names assigned from a `.casefold()` call, so `a_cf == b_cf` reads as a name comparison."""
    return {
        target.id
        for node in ast.walk(function)
        if isinstance(node, ast.Assign) and _is_casefold(node.value)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _compares_two_names(function: ast.AST) -> bool:
    folded = _casefolded_names(function)

    def is_folded(node: ast.expr) -> bool:
        return _is_casefold(node) or (isinstance(node, ast.Name) and node.id in folded)

    return any(
        isinstance(node, ast.Compare)
        and any(isinstance(op, ast.Eq) for op in node.ops)
        and is_folded(node.left)
        and any(is_folded(comparator) for comparator in node.comparators)
        for node in ast.walk(function)
    )


def _refuses_several_matches(function: ast.AST) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Call):
            call = node.left
            if isinstance(call.func, ast.Name) and call.func.id == "len":
                more_than_one = (ast.Gt, 1), (ast.GtE, 2)
                if any(
                    isinstance(op, kind) and isinstance(c, ast.Constant) and c.value == limit
                    for op, c in zip(node.ops, node.comparators, strict=True)
                    for kind, limit in more_than_one
                ):
                    return True
    return False


def _functions_comparing_names() -> list[tuple[str, str, bool]]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _compares_two_names(node):
                found.append((path.name, node.name, _refuses_several_matches(node)))
    return found


def test_every_function_that_compares_two_names_refuses_several_matches_or_is_listed() -> None:
    functions = _functions_comparing_names()

    assert len(functions) >= 8, "the scan found too few name comparisons to be reading the source"
    unguarded = [
        f"{file}:{name}" for file, name, refuses in functions if not refuses and name not in UNIQUE_BY_OPENPROJECT
    ]
    assert unguarded == [], "raise InvalidInputError when len(matches) > 1, or list the function with the reason"


def test_no_listed_function_has_stopped_comparing_names() -> None:
    comparing = {name for _file, name, _refuses in _functions_comparing_names()}

    assert set(UNIQUE_BY_OPENPROJECT) <= comparing


def test_the_scan_tells_a_guarded_comparison_from_an_unguarded_one() -> None:
    guarded = ast.parse(
        "def f(a, b, matches):\n    m = [x for x in a if x.casefold() == b.casefold()]\n    if len(m) > 1:\n        raise ValueError\n"
    ).body[0]
    unguarded = ast.parse("def f(a, b):\n    return [x for x in a if x.casefold() == b.casefold()][0]\n").body[0]

    assert _compares_two_names(guarded) and _refuses_several_matches(guarded)
    assert _compares_two_names(unguarded) and not _refuses_several_matches(unguarded)


def test_the_scan_follows_casefolded_variables_and_the_two_or_more_form() -> None:
    folded = ast.parse(
        "def f(a, b):\n    wanted = b.casefold()\n    hits = []\n    for x in a:\n        name = x.casefold()\n"
        "        if name == wanted:\n            hits.append(x)\n    if len(hits) >= 2:\n        raise ValueError\n"
    ).body[0]
    unrefused = ast.parse(
        "def f(a, b):\n    wanted = b.casefold()\n    return [x for x in a if x.casefold() == wanted][0]\n"
    ).body[0]

    assert _compares_two_names(folded) and _refuses_several_matches(folded)
    assert _compares_two_names(unrefused) and not _refuses_several_matches(unrefused)
