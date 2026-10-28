from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError, ProjectScopeDeniedError
from openproject_ce_mcp.app.ports.query_star_api import QueryStarRecord
from openproject_ce_mcp.app.services.query_star_service import QueryStarService
from openproject_ce_mcp.models import CurrentUser

IDENTIFIERS = {6: "demo", 7: "other"}
CALLER_ID = 5
DEMO = {"href": "/api/v3/projects/6", "title": "Demo"}
OTHER = {"href": "/api/v3/projects/7", "title": "Other"}


def _record(
    *,
    starred: bool = False,
    public: bool = False,
    project_link: dict | None = DEMO,
    owner_id: int | None = CALLER_ID,
    can_star: bool = True,
    can_unstar: bool = True,
) -> QueryStarRecord:
    return QueryStarRecord(
        query_id=3,
        starred=starred,
        public=public,
        project_link=project_link,
        owner_id=owner_id,
        can_star=can_star,
        can_unstar=can_unstar,
    )


class _FakeQueryStarApi:
    def __init__(self, record: QueryStarRecord) -> None:
        self._record = record
        self.get_calls: list[int] = []
        self.writes: list[tuple[int, bool]] = []

    async def get(self, query_id: int) -> QueryStarRecord:
        self.get_calls.append(query_id)
        return self._record

    async def set_starred(self, query_id: int, *, starred: bool) -> None:
        self.writes.append((query_id, starred))


class _FakeCurrentUser:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> CurrentUser:
        self.calls += 1
        return CurrentUser(id=CALLER_ID, name="Caller", login="caller")


def _service(record: QueryStarRecord, **overrides) -> tuple[QueryStarService, _FakeQueryStarApi]:
    api = _FakeQueryStarApi(record)
    defaults = {"enable_work_package_write": True, "read_projects": ("demo",), "write_projects": ("demo",)}
    settings = dataclasses.replace(make_settings(), **{**defaults, **overrides})
    service = QueryStarService(
        api=api, settings=settings, project_id_to_identifier=IDENTIFIERS, current_user=_FakeCurrentUser()
    )
    return service, api


@pytest.mark.asyncio
async def test_a_preview_names_the_wanted_state_and_writes_nothing() -> None:
    service, api = _service(_record())

    result = await service.set_starred(3, starred=True)

    assert (result.action, result.state, result.query_id, result.starred) == ("set_starred", "preview", 3, True)
    assert "confirm=true" in result.message
    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("wanted", [True, False])
async def test_a_confirmed_call_writes_the_wanted_state(wanted: bool) -> None:
    service, api = _service(_record(starred=not wanted))

    result = await service.set_starred(3, starred=wanted, confirm=True)

    assert result.state == "confirmed"
    assert api.writes == [(3, wanted)]


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_a_query_already_in_the_wanted_state_is_left_alone(confirm: bool) -> None:
    service, api = _service(_record(starred=True, can_star=False))

    result = await service.set_starred(3, starred=True, confirm=confirm)

    assert "already starred" in result.message
    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starred", "wanted", "record_kwargs"),
    [(False, True, {"can_star": False}), (True, False, {"can_unstar": False})],
)
@pytest.mark.parametrize("confirm", [False, True])
async def test_a_caller_without_the_link_of_the_wanted_state_is_refused_in_the_preview_too(
    starred: bool, wanted: bool, record_kwargs: dict, confirm: bool
) -> None:
    service, api = _service(_record(starred=starred, **record_kwargs))

    with pytest.raises(PermissionDeniedError, match="does not allow"):
        await service.set_starred(3, starred=wanted, confirm=confirm)

    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_a_query_of_a_project_outside_the_write_allowlist_is_refused(confirm: bool) -> None:
    service, api = _service(_record(project_link=OTHER, public=True))

    with pytest.raises(ProjectScopeDeniedError):
        await service.set_starred(3, starred=True, confirm=confirm)

    assert api.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("confirm", [False, True])
async def test_a_public_query_without_a_project_needs_the_write_scope_all(confirm: bool) -> None:
    service, api = _service(_record(project_link=None, public=True))

    with pytest.raises(ProjectScopeDeniedError):
        await service.set_starred(3, starred=True, confirm=confirm)
    assert api.writes == []

    everywhere, everywhere_api = _service(
        _record(project_link=None, public=True), write_projects=("*",), read_projects=("*",)
    )
    await everywhere.set_starred(3, starred=True, confirm=True)
    assert everywhere_api.writes == [(3, True)]


@pytest.mark.asyncio
@pytest.mark.parametrize("project_link", [None, DEMO])
async def test_a_private_query_of_the_caller_is_starred(project_link: dict | None) -> None:
    service, api = _service(_record(project_link=project_link, public=False))

    await service.set_starred(3, starred=True, confirm=True)

    assert api.writes == [(3, True)]


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_id", [9, None])
@pytest.mark.parametrize("project_link", [None, DEMO])
@pytest.mark.parametrize("confirm", [False, True])
async def test_a_private_query_of_another_user_or_of_unknown_owner_is_refused_in_the_preview_too(
    owner_id: int | None, project_link: dict | None, confirm: bool
) -> None:
    service, api = _service(_record(project_link=project_link, public=False, owner_id=owner_id))

    with pytest.raises(PermissionDeniedError, match="private"):
        await service.set_starred(3, starred=True, confirm=confirm)

    assert api.writes == []


@pytest.mark.asyncio
async def test_a_public_query_is_judged_without_reading_the_current_user() -> None:
    api = _FakeQueryStarApi(_record(public=True, owner_id=9))
    current_user = _FakeCurrentUser()
    settings = dataclasses.replace(
        make_settings(), enable_work_package_write=True, read_projects=("demo",), write_projects=("demo",)
    )
    service = QueryStarService(
        api=api, settings=settings, project_id_to_identifier=IDENTIFIERS, current_user=current_user
    )

    await service.set_starred(3, starred=True, confirm=True)

    assert current_user.calls == 0
    assert api.writes == [(3, True)]


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["enable_work_package_write", "enable_work_package_read"])
async def test_both_switches_of_the_work_package_scope_are_required(switch: str) -> None:
    service, api = _service(_record(), **{switch: False})

    with pytest.raises(PermissionDeniedError):
        await service.set_starred(3, starred=True)

    assert api.get_calls == []
