"""A write of one domain resolves names and "me" without the read gates of other domains.

Work package writes can be enabled while reads of users, versions, sprints or projects are off.
The lookups they use (`assignee="me"`, a version, sprint or project name) are internal: the gate of
a read tool belongs to that tool's service, so a lookup that checks it fails the write.
"""

from __future__ import annotations

import ast
import dataclasses

import httpx
import pytest
from _client_test_helpers import make_settings
from _source_scan import APP, calls_named, matching_nodes

from openproject_ce_mcp.client import OpenProjectClient

GATES = ("ensure_read_enabled", "ensure_write_enabled")


def _gates_in_resolvers(source: str | None = None) -> dict[str, list[ast.AST]]:
    found: dict[str, list[ast.AST]] = {}
    for gate in GATES:
        for name, nodes in matching_nodes(calls_named(gate), directories=(APP / "resolvers",), source=source).items():
            found.setdefault(name, []).extend(nodes)
    return found


def test_no_resolver_or_lookup_helper_checks_an_access_gate() -> None:
    assert _gates_in_resolvers() == {}, "the gate belongs to the tool's service, see the module docstring"


@pytest.mark.parametrize("gate", GATES)
def test_a_gate_inside_a_lookup_is_found(gate: str) -> None:
    planted = f"async def resolve(self):\n    access.{gate}('version', settings=self._settings)\n"

    assert list(_gates_in_resolvers(planted)) == ["planted.py:resolve"]


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v3/users/me":
        return httpx.Response(200, json={"id": 42, "name": "Ada", "login": "ada", "_links": {}}, request=request)
    raise AssertionError(f"Unexpected request: {request.method} {request.url}")


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["enable_membership_read", "enable_project_read", "enable_version_read"])
async def test_assignee_me_resolves_with_every_read_group_but_the_work_package_one_disabled(flag: str) -> None:
    settings = dataclasses.replace(make_settings(), **{flag: False})
    client = OpenProjectClient(settings, transport=httpx.MockTransport(_handler))

    assert await client._assignee_resolver.resolve_id("me") == "42"
    await client.aclose()
