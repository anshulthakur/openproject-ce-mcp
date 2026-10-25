"""The project link of a version, sprint or backlog bucket is checked by one contract.

OpenProject 16.x leaves the link out and 17.x renders an undisclosed placeholder when the token
cannot see the defining project. The required-link check treats the first as a violation, so a call
that checks a defining link with it behaves differently per release under the read scope `*`.
"""

from __future__ import annotations

import ast

import pytest
from _source_scan import APP

PLAIN_CHECKS = {
    "ensure_project_link_allowed",
    "project_link_allowed",
    "ensure_project_write_link_allowed",
    "project_link_payload_allowed",
}
DIRECTORIES = (APP / "policies", APP / "resolvers", APP / "services", APP / "adapters")


def _names_a_defining_link(node: ast.AST, tainted: set[str]) -> bool:
    return "defining" in ast.unparse(node).lower() or (isinstance(node, ast.Name) and node.id in tainted)


def _offenders(source: str | None = None) -> list[str]:
    """`file:function` of every function that passes a defining link, directly or through a variable
    assigned from one, to a plain required-link check, whichever way the argument is given."""
    sources = (
        {"planted.py": source}
        if source is not None
        else {p.name: p.read_text() for directory in DIRECTORIES for p in sorted(directory.glob("*.py"))}
    )
    found: list[str] = []
    for name, text in sources.items():
        for function in ast.walk(ast.parse(text)):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            tainted = {
                target.id
                for node in ast.walk(function)
                if isinstance(node, ast.Assign) and "defining" in ast.unparse(node.value).lower()
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            for node in ast.walk(function):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                callee = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
                if callee in PLAIN_CHECKS and any(_names_a_defining_link(arg, tainted) for arg in arguments):
                    found.append(f"{name}:{function.name}")
    return sorted(set(found))


def test_no_defining_project_link_goes_through_the_plain_required_link_check() -> None:
    assert _offenders() == [], "use ensure_defining_project_link_allowed or defining_project_link_allowed"


@pytest.mark.parametrize(
    "body",
    [
        "return ensure_project_link_allowed(record.defining_project_link, settings=s, project_id_to_identifier=i)",
        "return scope.project_link_allowed(version.defining_workspace_link, settings=s, project_id_to_identifier=i)",
        "return ensure_project_link_allowed(links['definingProject'], settings=s, project_id_to_identifier=i)",
        "return ensure_project_link_allowed(link=record.defining_project_link, settings=s, project_id_to_identifier=i)",
        "return project_link_payload_allowed(payload, link_key='definingProject', settings=s, project_id_to_identifier=i)",
        "link = record.defining_project_link\n    return ensure_project_link_allowed(link, settings=s, project_id_to_identifier=i)",
    ],
)
def test_a_plain_check_of_a_defining_link_is_found(body: str) -> None:
    source = f"def check(record, version, links, payload, s, i):\n    {body}\n"

    assert _offenders(source) == ["planted.py:check"]


def test_a_plain_check_of_an_ordinary_project_link_is_not_flagged() -> None:
    source = "def check(record, s, i):\n    return ensure_project_link_allowed(record.project_link, settings=s)\n"

    assert _offenders(source) == []
