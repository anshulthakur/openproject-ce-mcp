"""Every link whose title an adapter reads is classified.

A link title is the name or subject of what the link points to, and a link can point into a
project the read allowlist does not cover. An adapter that starts reading a new link's title
fails this test until the link is classified here with the reason it is safe, so the question is
asked once per link and not after a leak.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ADAPTERS = Path(__file__).resolve().parents[1] / "src" / "openproject_ce_mcp" / "app" / "adapters"

_INSTANCE_WIDE = "the resource is seen alike by every user of the instance"
_ANCHOR = "the project the record itself belongs to, which the service checks"
_CHECKED = "the service checks the project of this record or of its other end before it is returned"
_REDUCED = "the service or the adapter reduces it for projects the read scope does not cover"

# link name (camelCase, `_link` suffix removed) -> why reading its title is safe
CLASSIFIED: dict[str, str] = {
    "activity": _INSTANCE_WIDE,
    "assignee": _INSTANCE_WIDE,
    "authSource": _INSTANCE_WIDE,
    "author": _INSTANCE_WIDE,
    "category": _ANCHOR,
    "costType": _INSTANCE_WIDE,
    "defaultAssignee": _INSTANCE_WIDE,
    "definingProject": _CHECKED + " (version policy, per record)",
    "filter": _INSTANCE_WIDE + " (the filter's own name)",
    "githubUser": _INSTANCE_WIDE,
    "gitlabUser": _INSTANCE_WIDE,
    "mergedBy": _INSTANCE_WIDE,
    "operator": _INSTANCE_WIDE,
    "parent": _REDUCED + " (project parent)",
    "phaseDefinition": _INSTANCE_WIDE,
    "presenter": _INSTANCE_WIDE,
    "principal": _INSTANCE_WIDE,
    "priority": _INSTANCE_WIDE,
    "project": _ANCHOR,
    "projectPhase": _ANCHOR,
    "provider": _INSTANCE_WIDE,
    "query": _CHECKED + " (view: its project)",
    "responsible": _INSTANCE_WIDE,
    "self": _INSTANCE_WIDE,
    "sprint": "named on a work package the caller may read; the sprint object itself is checked on get",
    "status": _INSTANCE_WIDE,
    "storage": _INSTANCE_WIDE,
    "type": _INSTANCE_WIDE,
    "user": _INSTANCE_WIDE,
    "version": "named on a work package the caller may read; the version object itself is checked on get",
    "workspace": _CHECKED + " (sprint and backlog bucket policy, per record)",
    "entity": _CHECKED + " (the entity sits in the record's project)",
    "resource": _CHECKED + " (the notification's own project)",
    "from": _CHECKED + " (both relation ends)",
    "to": _CHECKED + " (both relation ends)",
    "column": _INSTANCE_WIDE,
    "context": _CHECKED + " (capability lists are filtered by project)",
    # loop variables over lists of links; the list is named where it is read
    "item": _REDUCED + " (time entry activity projects, work package children and ancestors)",
    "value": _REDUCED + " (board filter values)",
    "link": _REDUCED + " (time entry activity projects)",
}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _link_name(argument: ast.expr) -> str | None:
    """The link a `_link_title(...)` argument reads: a string key, or the variable's own name."""
    if isinstance(argument, ast.Name):
        return _camel(re.sub(r"_link$", "", argument.id))
    node: ast.expr | None = argument
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return None


def _titled_links() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in sorted(ADAPTERS.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if called not in ("_link_title", "link_title"):
                continue
            name = _link_name(node.args[0])
            assert name is not None, f"{path.name}:{node.lineno} reads a link title the audit cannot name"
            found.setdefault(name, set()).add(path.name)
    return found


def test_every_link_whose_title_an_adapter_reads_is_classified() -> None:
    found = _titled_links()

    assert len(found) > 25, "the scan found too few links to be reading the adapters"
    unclassified = {name: sorted(files) for name, files in found.items() if name not in CLASSIFIED}
    assert unclassified == {}, "classify these links in CLASSIFIED with the reason their title is safe"


def test_no_classification_outlives_the_link_it_describes() -> None:
    stale = sorted(set(CLASSIFIED) - set(_titled_links()))

    assert stale == []


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ('_link_title(links.get("parent"))', "parent"),
        ('link_title(payload["_links"]["version"])', "version"),
        ("_link_title(project_link)", "project"),
        ("_link_title(default_assignee_link)", "defaultAssignee"),
    ],
)
def test_the_scan_names_the_link_in_every_spelling_the_adapters_use(source: str, name: str) -> None:
    call = ast.parse(source).body[0].value  # type: ignore[attr-defined]

    assert _link_name(call.args[0]) == name


def test_the_scan_refuses_a_spelling_it_cannot_name() -> None:
    call = ast.parse("_link_title(links.get(key))").body[0].value  # type: ignore[attr-defined]

    assert _link_name(call.args[0]) is None
