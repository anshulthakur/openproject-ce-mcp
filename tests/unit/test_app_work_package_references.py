"""The decision which versions and sprints a work package result may name."""

from __future__ import annotations

import dataclasses

import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.app.errors import TransportError
from openproject_ce_mcp.app.ports.scoped_reference import ScopedReference, VisibleReferences
from openproject_ce_mcp.app.ports.work_package_api import WorkPackageGroupRecord, WorkPackageRecord
from openproject_ce_mcp.app.services._work_package_references import groups_for_result, visible_references

SECRET = ScopedReference("version", 7)
OWN = ScopedReference("version", 8)
SPRINT = ScopedReference("sprint", 3)


def _record(references: dict[str, frozenset[ScopedReference]], seeds=None) -> WorkPackageRecord:
    return WorkPackageRecord(
        id=1,
        project="Demo",
        references=references,
        seeds=seeds or {},
        payload={},
        summary_factory=lambda _visible: None,  # type: ignore[arg-type,return-value]
        detail_factory=lambda _visible: None,  # type: ignore[arg-type,return-value]
    )


class _Check:
    def __init__(self, outcomes: dict[ScopedReference, bool | Exception]) -> None:
        self._outcomes = outcomes
        self.calls: list[tuple[list[ScopedReference], dict]] = []

    async def __call__(self, references, *, seeds):
        asked = list(references)
        self.calls.append((asked, dict(seeds)))
        return {reference: self._outcomes[reference] for reference in asked}


def _settings(**changes):
    return dataclasses.replace(make_settings(), read_projects=("demo",), **changes)


@pytest.mark.asyncio
async def test_everything_is_visible_under_a_wildcard_scope_without_a_request() -> None:
    check = _Check({})
    settings = dataclasses.replace(make_settings(), read_projects=("*",))

    visible = await visible_references(
        records=[_record({"target_versions": frozenset({SECRET})})], settings=settings, check=check
    )

    assert visible.contains(SECRET) and visible.contains(SPRINT)
    assert check.calls == []


@pytest.mark.asyncio
async def test_only_the_references_the_check_allows_are_visible() -> None:
    check = _Check({SECRET: False, OWN: True})

    visible = await visible_references(
        records=[_record({"target_versions": frozenset({SECRET, OWN})})], settings=_settings(), check=check
    )

    assert (visible.contains(SECRET), visible.contains(OWN), visible.contains(SPRINT)) == (False, True, False)


@pytest.mark.asyncio
async def test_a_reference_of_several_records_is_asked_once_with_the_seeds_of_all() -> None:
    seed = {"_links": {}}
    check = _Check({SECRET: True})

    await visible_references(
        records=[
            _record({"version": frozenset({SECRET})}, {SECRET: seed}),
            _record({"target_versions": frozenset({SECRET})}),
        ],
        settings=_settings(),
        check=check,
    )

    assert check.calls == [([SECRET], {SECRET: seed})]


@pytest.mark.asyncio
async def test_no_check_is_made_when_no_record_names_a_reference() -> None:
    check = _Check({})

    visible = await visible_references(records=[_record({})], settings=_settings(), check=check)

    assert not visible.contains(SECRET)
    assert check.calls == []


@pytest.mark.asyncio
async def test_a_failed_check_fails_the_whole_decision() -> None:
    check = _Check({SECRET: True, OWN: TransportError("timeout")})

    with pytest.raises(TransportError):
        await visible_references(
            records=[_record({"target_versions": frozenset({SECRET, OWN})})], settings=_settings(), check=check
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hidden", "field"),
    [
        ({"hide_work_package_fields": ("version",)}, "target_versions"),
        ({"hide_work_package_fields": ("target_versions",)}, "version"),
        ({"hide_work_package_fields": ("sprint",)}, "sprint"),
        ({"hide_work_package_fields": ("custom_fields",)}, "customField5"),
        ({"hide_custom_fields": ("customField5",)}, "customField5"),
    ],
)
async def test_a_field_a_hide_setting_removes_costs_no_check_and_cannot_fail_the_read(hidden, field) -> None:
    check = _Check({SECRET: TransportError("timeout")})

    visible = await visible_references(
        records=[_record({field: frozenset({SECRET})})], settings=_settings(**hidden), check=check
    )

    assert check.calls == []
    assert not visible.contains(SECRET)


@pytest.mark.asyncio
async def test_a_shown_field_next_to_a_hidden_one_is_still_checked() -> None:
    check = _Check({SECRET: True, OWN: True})

    await visible_references(
        records=[_record({"sprint": frozenset({SECRET}), "customField5": frozenset({OWN})})],
        settings=_settings(hide_work_package_fields=("sprint",)),
        check=check,
    )

    assert check.calls[0][0] == [OWN]


@pytest.mark.asyncio
async def test_the_references_of_groups_are_checked_with_those_of_the_records() -> None:
    check = _Check({SECRET: False, OWN: True})
    group = WorkPackageGroupRecord(value="Secret", count=1, sums=None, references=frozenset({SECRET}))

    visible = await visible_references(
        records=[_record({"target_versions": frozenset({OWN})})], groups=[group], settings=_settings(), check=check
    )

    assert check.calls[0][0] == [OWN, SECRET]
    assert not visible.contains(SECRET)


def _group(value, *references: ScopedReference) -> WorkPackageGroupRecord:
    return WorkPackageGroupRecord(value=value, count=2, sums={"estimatedTime": "P1D"}, references=frozenset(references))


def test_groups_are_returned_as_the_server_sent_them_when_every_label_is_visible() -> None:
    groups = groups_for_result(
        [_group("Own", OWN), _group(None)], group_by="version", visible=VisibleReferences.only([OWN])
    )

    assert [(g.value, g.count, g.sums) for g in groups or []] == [
        ("Own", 2, {"estimatedTime": "P1D"}),
        (None, 2, {"estimatedTime": "P1D"}),
    ]


@pytest.mark.parametrize("group_by", ["version", "target_versions", "sprint", "status", None])
def test_all_groups_are_dropped_when_one_names_a_reference_that_is_not_visible(group_by) -> None:
    groups = [_group("Own", OWN), _group("Secret", SECRET)]

    assert groups_for_result(groups, group_by=group_by, visible=VisibleReferences.only([OWN])) is None


@pytest.mark.parametrize("group_by", ["version", "target_versions", "observed_in_versions", "sprint", "backlog_bucket"])
def test_all_groups_are_dropped_when_a_label_of_a_reference_column_has_no_link_to_check(group_by) -> None:
    assert groups_for_result([_group("Mystery")], group_by=group_by, visible=VisibleReferences.everything()) is None


@pytest.mark.parametrize("group_by", ["status", "assignee", "project", "category", None])
def test_a_label_without_a_link_is_kept_in_a_column_that_names_no_version_or_sprint(group_by) -> None:
    groups = groups_for_result([_group("Open")], group_by=group_by, visible=VisibleReferences.only([]))

    assert [g.value for g in groups or []] == ["Open"]
