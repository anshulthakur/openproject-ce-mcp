from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import NotFoundError, PermissionDeniedError, TransportError
from openproject_ce_mcp.app.ports.scoped_reference import ScopedReference
from openproject_ce_mcp.app.resolvers.scoped_reference_resolver import ScopedReferenceResolver

OWN_VERSION = ScopedReference("version", 1)
FOREIGN_VERSION = ScopedReference("version", 2)
MISSING_LINK_VERSION = ScopedReference("version", 3)
OWN_SPRINT = ScopedReference("sprint", 4)
FOREIGN_SPRINT = ScopedReference("sprint", 5)
PROJECTS = {1: "demo", 9: "secret"}


def _project(project_id: int) -> dict:
    return {"href": f"/api/v3/projects/{project_id}"}


class _VersionApi:
    def __init__(self, links: dict[int, object]) -> None:
        self._links = links
        self.calls: list[int] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def get(self, version_id: int):
        self.calls.append(version_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        outcome = self._links[version_id]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(defining_project_link=outcome)


class _SprintApi:
    def __init__(self, links: dict[int, object]) -> None:
        self._links = links
        self.calls: list[int] = []

    async def get(self, sprint_id: int):
        self.calls.append(sprint_id)
        outcome = self._links[sprint_id]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(defining_workspace_link=outcome, defining_workspace_payload=None)


def _resolver(versions=None, sprints=None, *, read_projects=("demo",)) -> ScopedReferenceResolver:
    return ScopedReferenceResolver(
        version_api=_VersionApi(versions if versions is not None else {}),  # type: ignore[arg-type]
        sprint_api=_SprintApi(sprints if sprints is not None else {}),  # type: ignore[arg-type]
        settings=dataclasses.replace(make_settings(), read_projects=read_projects),
        project_id_to_identifier=PROJECTS,
    )


@pytest.mark.asyncio
async def test_a_reference_is_allowed_when_its_defining_project_is_covered() -> None:
    resolver = _resolver(
        {1: _project(1), 2: _project(9), 3: None},
        {4: _project(1), 5: _project(9)},
    )

    outcomes = await resolver.references_allowed(
        [OWN_VERSION, FOREIGN_VERSION, MISSING_LINK_VERSION, OWN_SPRINT, FOREIGN_SPRINT], seeds={}
    )

    assert outcomes == {
        OWN_VERSION: True,
        FOREIGN_VERSION: False,
        MISSING_LINK_VERSION: False,
        OWN_SPRINT: True,
        FOREIGN_SPRINT: False,
    }


@pytest.mark.asyncio
async def test_a_reference_is_looked_up_once_however_often_it_is_named() -> None:
    resolver = _resolver({1: _project(1)})

    await resolver.references_allowed([OWN_VERSION, OWN_VERSION, OWN_VERSION], seeds={})

    assert resolver._version_api.calls == [1]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_version_the_token_cannot_see_is_not_allowed() -> None:
    resolver = _resolver({1: NotFoundError("gone")}, {4: NotFoundError("gone")})

    outcomes = await resolver.references_allowed([OWN_VERSION, OWN_SPRINT], seeds={})

    assert outcomes == {OWN_VERSION: False, OWN_SPRINT: False}


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TransportError("timeout"), PermissionDeniedError("denied")])
async def test_any_other_failure_is_returned_for_the_caller_to_raise_and_does_not_hide_the_others(error) -> None:
    resolver = _resolver({1: error, 2: _project(1)})

    outcomes = await resolver.references_allowed([OWN_VERSION, FOREIGN_VERSION], seeds={})

    assert outcomes[OWN_VERSION] is error
    assert outcomes[FOREIGN_VERSION] is True


@pytest.mark.asyncio
async def test_a_seed_is_judged_without_a_request() -> None:
    resolver = _resolver()
    seeds = {
        OWN_VERSION: {"_links": {"definingProject": _project(1)}},
        FOREIGN_VERSION: {"_links": {"definingProject": _project(9)}},
        MISSING_LINK_VERSION: {"_links": {}},
        OWN_SPRINT: {"_links": {"definingWorkspace": _project(1)}},
        FOREIGN_SPRINT: {"_links": {"definingWorkspace": _project(9)}},
    }

    outcomes = await resolver.references_allowed(seeds, seeds=seeds)

    assert outcomes == {
        OWN_VERSION: True,
        FOREIGN_VERSION: False,
        MISSING_LINK_VERSION: False,
        OWN_SPRINT: True,
        FOREIGN_SPRINT: False,
    }
    assert resolver._version_api.calls == [] and resolver._sprint_api.calls == []  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_sprint_seed_with_an_embedded_defining_workspace_is_judged_by_that_object() -> None:
    resolver = _resolver()
    seed = {
        "_links": {"definingWorkspace": _project(1)},
        "_embedded": {
            "definingWorkspace": {"id": 1, "identifier": "demo", "name": "Demo", "_links": {"self": _project(1)}}
        },
    }

    assert await resolver.references_allowed([OWN_SPRINT], seeds={OWN_SPRINT: seed}) == {OWN_SPRINT: True}


@pytest.mark.asyncio
async def test_the_requests_of_one_call_run_concurrently_but_at_most_ten_at_a_time() -> None:
    versions = {i: _project(1) for i in range(1, 31)}
    resolver = _resolver(versions)

    outcomes = await resolver.references_allowed([ScopedReference("version", i) for i in versions], seeds={})

    assert all(outcomes.values())
    assert 1 < resolver._version_api.max_in_flight <= 10  # type: ignore[attr-defined]
