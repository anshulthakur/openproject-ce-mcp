from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import PermissionDeniedError
from openproject_ce_mcp.app.ports.activity_api import ActivityRecord
from openproject_ce_mcp.app.services.activity_service import ActivityService
from openproject_ce_mcp.models import ActivitySummary


def _summary(activity_id: int, *, details: bool = True) -> ActivitySummary:
    return ActivitySummary(
        id=activity_id,
        type="Activity::Comment",
        version=activity_id,
        user="Alice",
        comment=f"comment {activity_id}",
        created_at="2026-01-01T00:00:00Z",
        details=[{"raw": "Parent set to FOREIGN"}] if details else None,
        details_omitted=not details,
    )


class _FakeActivityApi:
    def __init__(self, count: int = 3) -> None:
        self._count = count
        self.list_for_work_package_calls: list[int] = []
        self.to_summary_calls: list[int] = []
        self.details_requested: list[bool] = []

    async def list_for_work_package(self, work_package_id: int) -> list[ActivityRecord]:
        self.list_for_work_package_calls.append(work_package_id)

        def make_record(activity_id: int) -> ActivityRecord:
            def to_summary(text_limit: int | None, *, details: bool) -> ActivitySummary:
                self.to_summary_calls.append(activity_id)
                self.details_requested.append(details)
                return _summary(activity_id, details=details)

            return ActivityRecord(to_summary=to_summary)

        return [make_record(i) for i in range(1, self._count + 1)]


def _resolve_work_package_id_ok(resolved_id: int = 9):
    calls: list[tuple[int | str, bool]] = []

    async def resolve(work_package_ref: int | str, *, write: bool = False) -> int:
        calls.append((work_package_ref, write))
        return resolved_id

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


def _resolve_work_package_id_denied():
    async def resolve(work_package_ref: int | str, *, write: bool = False) -> int:
        raise PermissionDeniedError("OpenProject access to this project is disabled by OPENPROJECT_READ_PROJECTS.")

    return resolve


def _service(*, api: _FakeActivityApi | None = None, settings=None, resolve_work_package_id=None) -> ActivityService:
    return ActivityService(
        api=api or _FakeActivityApi(),
        settings=settings or make_settings(),
        resolve_work_package_id=resolve_work_package_id or _resolve_work_package_id_ok(),
    )


@pytest.mark.asyncio
async def test_list_for_work_package_resolves_anchor_with_write_false() -> None:
    resolver = _resolve_work_package_id_ok(resolved_id=9)
    service = _service(resolve_work_package_id=resolver)

    await service.list_for_work_package(9)

    assert resolver.calls == [(9, False)]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_list_for_work_package_denies_anchor_outside_read_allowlist() -> None:
    api = _FakeActivityApi()
    service = _service(api=api, resolve_work_package_id=_resolve_work_package_id_denied())

    with pytest.raises(PermissionDeniedError):
        await service.list_for_work_package(9)

    assert api.list_for_work_package_calls == []


@pytest.mark.asyncio
async def test_list_for_work_package_returns_newest_first_bounded_by_limit() -> None:
    """Verbatim of client.py's original: elements[-effective_limit:], then
    reversed(...) -- the most recent activities first, bounded by limit."""
    api = _FakeActivityApi(count=5)
    service = _service(api=api)

    result = await service.list_for_work_package(9, limit=2)

    assert result.count == 2
    assert [r.id for r in result.results] == [5, 4]


@pytest.mark.asyncio
async def test_list_for_work_package_only_normalizes_survivors_of_slicing() -> None:
    """The eager-vs-lazy regression this migration exists to avoid: to_summary
    must be called ONLY on the elements that survive slicing, never on every
    element the API returned."""
    api = _FakeActivityApi(count=5)
    service = _service(api=api)

    await service.list_for_work_package(9, limit=2)

    assert sorted(api.to_summary_calls) == [4, 5]


@pytest.mark.asyncio
async def test_list_for_work_package_passes_text_limit_through_to_summary() -> None:
    seen_limits: list[int | None] = []
    api = _FakeActivityApi(count=1)
    original_list = api.list_for_work_package

    async def wrapped(work_package_id: int):
        records = await original_list(work_package_id)

        def wrap(record):
            def to_summary(text_limit, *, details):
                seen_limits.append(text_limit)
                return record.to_summary(text_limit, details=details)

            return ActivityRecord(to_summary=to_summary)

        return [wrap(r) for r in records]

    api.list_for_work_package = wrapped  # type: ignore[method-assign]
    service = _service(api=api)

    await service.list_for_work_package(9, text_limit=42)

    assert seen_limits == [42]


@pytest.mark.asyncio
async def test_list_for_work_package_uses_default_page_size_when_limit_none() -> None:
    settings = dataclasses.replace(make_settings(), default_page_size=2, max_page_size=5, max_results=5)
    service = _service(api=_FakeActivityApi(count=4), settings=settings)

    result = await service.list_for_work_package(9, limit=None)

    assert [r.id for r in result.results] == [4, 3]


# --- change details under the read scope --------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("read_projects", [("*",), (" * ",), ("demo", "*")])
async def test_details_are_served_when_the_read_scope_allows_all(read_projects: tuple[str, ...]) -> None:
    api = _FakeActivityApi(count=2)
    settings = dataclasses.replace(make_settings(), read_projects=read_projects)

    result = await _service(api=api, settings=settings).list_for_work_package(9)

    assert api.details_requested == [True, True]
    assert all(r.details == [{"raw": "Parent set to FOREIGN"}] and not r.details_omitted for r in result.results)


@pytest.mark.asyncio
@pytest.mark.parametrize("read_projects", [(), ("demo",), ("team-*",), ("**",)])
async def test_details_are_left_out_under_a_restricted_read_scope(read_projects: tuple[str, ...]) -> None:
    api = _FakeActivityApi(count=2)
    settings = dataclasses.replace(make_settings(), read_projects=read_projects)

    result = await _service(api=api, settings=settings).list_for_work_package(9)

    assert api.details_requested == [False, False]
    for row in result.results:
        assert row.details is None
        assert row.details_omitted is True
        assert row.comment and row.user == "Alice" and row.created_at


@pytest.mark.asyncio
async def test_details_are_left_out_when_a_work_package_field_is_hidden_even_under_all() -> None:
    api = _FakeActivityApi(count=1)
    settings = dataclasses.replace(
        make_settings(), read_projects=("*",), hidden_fields={"work_package": ("estimated_time",)}
    )

    result = await _service(api=api, settings=settings).list_for_work_package(9)

    assert api.details_requested == [False]
    assert result.results[0].details is None and result.results[0].details_omitted is True


@pytest.mark.asyncio
async def test_a_hidden_details_field_and_the_omitted_flag_are_independent() -> None:
    settings = dataclasses.replace(make_settings(), read_projects=("*",), hidden_fields={"activity": ("details",)})

    result = await _service(api=_FakeActivityApi(count=1), settings=settings).list_for_work_package(9)

    assert getattr(result.results[0], "_hidden_keys", frozenset()) == {"details"}
    assert result.results[0].details_omitted is False


@pytest.mark.asyncio
async def test_a_details_hide_pattern_hides_the_omitted_flag_too() -> None:
    settings = dataclasses.replace(make_settings(), hidden_fields={"activity": ("details*",)})

    result = await _service(api=_FakeActivityApi(count=1), settings=settings).list_for_work_package(9)

    assert getattr(result.results[0], "_hidden_keys", frozenset()) == {
        "details",
        "details_truncated",
        "details_omitted",
    }


# --- hidden fields ------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_for_work_package_masks_hidden_comment() -> None:
    """Regression: the app/ Service dropped
    client.py's original `self._apply_hidden_fields("activity", ...)` stamp
    that `normalize_activity` used to apply -- OPENPROJECT_HIDE_ACTIVITY_FIELDS
    would have silently stopped masking anything."""
    settings = dataclasses.replace(make_settings(), hidden_fields={"activity": ("comment",)})
    service = _service(api=_FakeActivityApi(count=1), settings=settings)

    result = await service.list_for_work_package(9)

    assert getattr(result.results[0], "_hidden_keys", frozenset()) == {"comment"}


@pytest.mark.asyncio
async def test_comment_hidden_by_activity_scope_not_time_entry_scope() -> None:
    settings_te_hidden = dataclasses.replace(make_settings(), hidden_fields={"time_entry": ("comment",)})
    service_te_hidden = _service(api=_FakeActivityApi(count=1), settings=settings_te_hidden)
    result_te_hidden = await service_te_hidden.list_for_work_package(9)
    assert getattr(result_te_hidden.results[0], "_hidden_keys", frozenset()) == frozenset()

    settings_activity_hidden = dataclasses.replace(make_settings(), hidden_fields={"activity": ("comment",)})
    service_activity_hidden = _service(api=_FakeActivityApi(count=1), settings=settings_activity_hidden)
    result_activity_hidden = await service_activity_hidden.list_for_work_package(9)
    assert getattr(result_activity_hidden.results[0], "_hidden_keys", frozenset()) == {"comment"}
