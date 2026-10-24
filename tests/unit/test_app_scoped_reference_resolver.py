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
OWN_BUCKET = ScopedReference("backlog_bucket", 6)
FOREIGN_BUCKET = ScopedReference("backlog_bucket", 7)
PROJECTS = {1: "demo", 9: "secret"}


def _project(project_id: int) -> dict:
    return {"href": f"/api/v3/projects/{project_id}"}


class _Api:
    """Answers `get` for versions, sprints or buckets from a table of project links or errors."""

    def __init__(self, links: dict[int, object], *, kind: str) -> None:
        self._links = links
        self._kind = kind
        self.calls: list[int] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def get(self, resource_id: int):
        self.calls.append(resource_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        outcome = self._links[resource_id]
        if isinstance(outcome, Exception):
            raise outcome
        if self._kind == "version":
            return SimpleNamespace(defining_project_link=outcome)
        return SimpleNamespace(defining_workspace_link=outcome, defining_workspace_payload=None)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _resolver(versions=None, sprints=None, buckets=None, *, read_projects=("demo",), clock=None, known=None):
    return ScopedReferenceResolver(
        version_api=_Api(versions or {}, kind="version"),  # type: ignore[arg-type]
        sprint_api=_Api(sprints or {}, kind="sprint"),  # type: ignore[arg-type]
        backlog_bucket_api=_Api(buckets or {}, kind="bucket"),  # type: ignore[arg-type]
        settings=dataclasses.replace(make_settings(), read_projects=read_projects),
        project_id_to_identifier=PROJECTS if known is None else known,
        **({"clock": clock} if clock else {}),
    )


@pytest.mark.asyncio
async def test_a_reference_is_allowed_when_its_defining_project_is_covered() -> None:
    resolver = _resolver(
        {1: _project(1), 2: _project(9), 3: None},
        {4: _project(1), 5: _project(9)},
        {6: _project(1), 7: _project(9)},
    )

    outcomes = await resolver.references_allowed(
        [OWN_VERSION, FOREIGN_VERSION, MISSING_LINK_VERSION, OWN_SPRINT, FOREIGN_SPRINT, OWN_BUCKET, FOREIGN_BUCKET]
    )

    assert outcomes == {
        OWN_VERSION: True,
        FOREIGN_VERSION: False,
        MISSING_LINK_VERSION: False,
        OWN_SPRINT: True,
        FOREIGN_SPRINT: False,
        OWN_BUCKET: True,
        FOREIGN_BUCKET: False,
    }


@pytest.mark.asyncio
async def test_a_missing_defining_project_link_is_covered_under_a_wildcard_scope() -> None:
    resolver = _resolver({3: None}, {4: None}, {6: None}, read_projects=("*",))

    outcomes = await resolver.references_allowed([MISSING_LINK_VERSION, OWN_SPRINT, OWN_BUCKET])

    assert set(outcomes.values()) == {True}


@pytest.mark.asyncio
async def test_a_reference_is_looked_up_once_however_often_it_is_named() -> None:
    resolver = _resolver({1: _project(1)})

    await resolver.references_allowed([OWN_VERSION, OWN_VERSION, OWN_VERSION])

    assert resolver._version_api.calls == [1]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_remembered_project_is_judged_again_without_a_request() -> None:
    resolver = _resolver({1: _project(1), 2: _project(9)})

    await resolver.references_allowed([OWN_VERSION, FOREIGN_VERSION])
    outcomes = await resolver.references_allowed([OWN_VERSION, FOREIGN_VERSION])

    assert outcomes == {OWN_VERSION: True, FOREIGN_VERSION: False}
    assert resolver._version_api.calls == [1, 2]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_the_verdict_follows_the_current_scope_and_directory_not_the_moment_of_the_lookup() -> None:
    known = {1: "demo"}
    resolver = _resolver({1: _project(1)}, known=known)
    assert await resolver.references_allowed([OWN_VERSION]) == {OWN_VERSION: True}

    resolver._settings = dataclasses.replace(resolver._settings, read_projects=("other",))
    assert await resolver.references_allowed([OWN_VERSION]) == {OWN_VERSION: False}
    assert resolver._version_api.calls == [1]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_remembered_project_expires_so_a_moved_sprint_is_noticed() -> None:
    clock = _Clock()
    resolver = _resolver(sprints={4: _project(1)}, clock=clock)
    await resolver.references_allowed([OWN_SPRINT])

    resolver._sprint_api._links[4] = _project(9)  # type: ignore[attr-defined]
    assert await resolver.references_allowed([OWN_SPRINT]) == {OWN_SPRINT: True}
    clock.now += 301
    assert await resolver.references_allowed([OWN_SPRINT]) == {OWN_SPRINT: False}
    assert resolver._sprint_api.calls == [4, 4]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_resource_the_token_cannot_see_is_not_allowed_and_is_remembered_as_such() -> None:
    resolver = _resolver({1: NotFoundError("gone")}, {4: NotFoundError("gone")}, {6: NotFoundError("gone")})

    first = await resolver.references_allowed([OWN_VERSION, OWN_SPRINT, OWN_BUCKET])
    second = await resolver.references_allowed([OWN_VERSION, OWN_SPRINT, OWN_BUCKET])

    assert first == second == {OWN_VERSION: False, OWN_SPRINT: False, OWN_BUCKET: False}
    assert resolver._version_api.calls == [1]  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TransportError("timeout"), PermissionDeniedError("denied")])
async def test_any_other_failure_is_returned_for_the_caller_to_raise_and_is_not_remembered(error) -> None:
    resolver = _resolver({1: error, 2: _project(1)})

    outcomes = await resolver.references_allowed([OWN_VERSION, FOREIGN_VERSION])
    assert outcomes[OWN_VERSION] is error
    assert outcomes[FOREIGN_VERSION] is True

    resolver._version_api._links[1] = _project(1)  # type: ignore[attr-defined]
    assert await resolver.references_allowed([OWN_VERSION]) == {OWN_VERSION: True}


@pytest.mark.asyncio
async def test_the_memory_is_bounded() -> None:
    from openproject_ce_mcp.app.resolvers import scoped_reference_resolver as module

    versions = {i: _project(1) for i in range(1, module._MAX_ENTRIES + 50)}
    resolver = _resolver(versions)

    await resolver.references_allowed([ScopedReference("version", i) for i in versions])

    assert len(resolver._known) == module._MAX_ENTRIES


@pytest.mark.asyncio
async def test_the_requests_of_one_call_run_concurrently_but_at_most_ten_at_a_time() -> None:
    versions = {i: _project(1) for i in range(1, 31)}
    resolver = _resolver(versions)

    outcomes = await resolver.references_allowed([ScopedReference("version", i) for i in versions])

    assert all(outcomes.values())
    assert 1 < resolver._version_api.max_in_flight <= 10  # type: ignore[attr-defined]
