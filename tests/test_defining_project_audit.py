"""The project link of a version, sprint or backlog bucket is checked by one contract.

OpenProject 16.x leaves the link out and 17.x renders an undisclosed placeholder when the token
cannot see the defining project. The required-link check treats the first as a violation, so a call
that checks a defining link with it behaves differently per release under the read scope `*`.
"""

from __future__ import annotations

import ast

import pytest
from _source_scan import APP, matching_nodes

PLAIN_CHECKS = {"ensure_project_link_allowed", "project_link_allowed", "ensure_project_write_link_allowed"}


def _plain_check_of_a_defining_link(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    return name in PLAIN_CHECKS and "defining" in ast.unparse(node.args[0]).lower()


def _offenders(source: str | None = None) -> dict[str, list[ast.AST]]:
    directories = (APP / "policies", APP / "resolvers", APP / "services", APP / "adapters")
    return matching_nodes(_plain_check_of_a_defining_link, directories=directories, source=source)


def test_no_defining_project_link_goes_through_the_plain_required_link_check() -> None:
    assert _offenders() == {}, "use ensure_defining_project_link_allowed or defining_project_link_allowed"


@pytest.mark.parametrize(
    "call",
    [
        "ensure_project_link_allowed(record.defining_project_link, settings=s, project_id_to_identifier=i)",
        "scope.project_link_allowed(version.defining_workspace_link, settings=s, project_id_to_identifier=i)",
        "ensure_project_link_allowed(links['definingProject'], settings=s, project_id_to_identifier=i)",
    ],
)
def test_a_plain_check_of_a_defining_link_is_found(call: str) -> None:
    assert list(_offenders(f"def check(record, version, links, s, i):\n    return {call}\n")) == ["planted.py:check"]
