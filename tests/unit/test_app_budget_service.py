from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError
from openproject_ce_mcp.app.services.budget_service import BudgetService
from openproject_ce_mcp.models import BudgetSummary
from openproject_ce_mcp.presentation import _to_payload


class _FakeBudgetApi:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None]] = []

    async def list_for_project(self, project_id: int, *, project_name: str | None) -> list[BudgetSummary]:
        self.calls.append((project_id, project_name))
        return [BudgetSummary(id=3, subject="Q4 hardware", project_id=project_id, project=project_name)]


async def _resolve_project_ref(project_ref: str, *, write: bool = False, context=None) -> dict:
    return {"id": 6, "identifier": project_ref, "name": "Demo Project", "_links": {}}


async def _denying_resolve_project_ref(project_ref: str, *, write: bool = False, context=None) -> dict:
    raise PermissionDeniedError("OPENPROJECT_READ_PROJECTS")


def _service(api: _FakeBudgetApi, *, settings=None, resolve_project_ref=_resolve_project_ref) -> BudgetService:
    return BudgetService(api=api, settings=settings or make_settings(), resolve_project_ref=resolve_project_ref)


@pytest.mark.asyncio
async def test_list_returns_the_budgets_of_the_resolved_project() -> None:
    api = _FakeBudgetApi()

    result = await _service(api).list("demo")

    assert result.count == 1
    assert (result.results[0].id, result.results[0].subject) == (3, "Q4 hardware")
    assert api.calls == [(6, "Demo Project")]


@pytest.mark.asyncio
async def test_list_hides_fields_through_the_budget_entity() -> None:
    settings = dataclasses.replace(make_settings(), hidden_fields={"budget": ("subject",)})

    result = await _service(_FakeBudgetApi(), settings=settings).list("demo")

    assert result.results[0]._hidden_keys == frozenset({"subject"})
    assert "subject" not in _to_payload(result.results[0])


@pytest.mark.asyncio
async def test_a_project_hide_setting_does_not_mask_budgets() -> None:
    settings = dataclasses.replace(make_settings(), hide_project_fields=("subject",))

    result = await _service(_FakeBudgetApi(), settings=settings).list("demo")

    assert getattr(result.results[0], "_hidden_keys", frozenset()) == frozenset()


@pytest.mark.asyncio
async def test_a_project_outside_the_read_allowlist_is_denied_before_any_request() -> None:
    api = _FakeBudgetApi()

    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        await _service(api, resolve_project_ref=_denying_resolve_project_ref).list("other")

    assert api.calls == []


@pytest.mark.asyncio
async def test_list_is_refused_when_project_reads_are_switched_off() -> None:
    api = _FakeBudgetApi()
    settings = dataclasses.replace(make_settings(), enable_project_read=False)

    with pytest.raises(PermissionDeniedError):
        await _service(api, settings=settings).list("demo")

    assert api.calls == []


@pytest.mark.asyncio
async def test_list_resolves_the_project_for_reading_not_writing() -> None:
    writes: list[bool] = []

    async def resolve(project_ref: str, *, write: bool = False, context=None) -> dict:
        writes.append(write)
        return await _resolve_project_ref(project_ref, write=write, context=context)

    await _service(_FakeBudgetApi(), resolve_project_ref=resolve).list("demo")

    assert writes == [False]
