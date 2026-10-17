"""Which columns sort_by and group_by accept, and the release each newer one needs."""

from __future__ import annotations

import httpx
import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.client import InvalidInputError, OpenProjectClient
from openproject_ce_mcp.tools_validation import _validate_group_by, _validate_sort_by
from openproject_ce_mcp.work_package_columns import (
    COLUMN_FLOORS,
    GROUPABLE_FIELDS,
    SORTABLE_FIELDS,
    floors_used,
    group_by_description,
    sort_by_description,
)

# Accepted by OpenProject 17.9.2, probed live: sortBy takes all of them, groupBy the second list.
_ADDED_SORTABLE = ["observed_in_versions", "target_versions", "position", "sprint", "backlog_bucket"]
_ADDED_GROUPABLE = ["observed_in_versions", "target_versions", "sprint", "backlog_bucket"]
# OpenProject rejects spent_hours and shared_with_users; the others are internal or
# only sort by the id (manual_sorting needs a saved query, parent falls back to id).
_NOT_OFFERED = ["spent_hours", "shared_with_users", "manual_sorting", "parent", "exact_match", "typeahead"]


@pytest.mark.parametrize("field", _ADDED_SORTABLE)
def test_sort_by_accepts_the_newer_columns(field: str) -> None:
    assert [c.field for c in _validate_sort_by([f"{field}:desc"]) or []] == [field]


@pytest.mark.parametrize("field", _ADDED_GROUPABLE)
def test_group_by_accepts_the_newer_columns(field: str) -> None:
    assert _validate_group_by(field) == field


@pytest.mark.parametrize("field", ["position", "story_points"])
def test_group_by_rejects_columns_that_only_sort(field: str) -> None:
    with pytest.raises(ValueError, match=f"group_by: unknown field '{field}'"):
        _validate_group_by(field)


@pytest.mark.parametrize("field", _NOT_OFFERED)
def test_columns_that_are_not_offered_stay_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="unknown field"):
        _validate_sort_by([field])
    with pytest.raises(ValueError, match="unknown field"):
        _validate_group_by(field)


def test_every_column_with_a_release_can_be_sorted_and_the_groupable_ones_are_sortable() -> None:
    assert set(COLUMN_FLOORS) <= SORTABLE_FIELDS
    assert GROUPABLE_FIELDS <= SORTABLE_FIELDS


def test_floors_used_lists_newer_columns_oldest_release_first() -> None:
    assert floors_used(["status", "sprint", "project_phase"], "observed_in_versions") == [
        ("project_phase", "16.1"),
        ("sprint", "17.4"),
        ("observed_in_versions", "17.9"),
    ]
    assert floors_used(["status", "id"], None) == []
    assert floors_used([], "sprint") == [("sprint", "17.4")]


def _listed_fields(description: str) -> set[str]:
    listed = description.split("Fields: ", 1)[-1] if "Fields: " in description else description.split(": ", 1)[1]
    return {name.strip() for name in listed.split(", or a custom field")[0].split(", ")}


def test_the_parameter_descriptions_list_exactly_the_fields_and_every_release() -> None:
    sort_text, group_text = sort_by_description(), group_by_description()

    assert _listed_fields(sort_text) == SORTABLE_FIELDS
    assert _listed_fields(group_text) == GROUPABLE_FIELDS
    for text in (sort_text, group_text):
        assert all(f"{field} {floor}+" in text for field, floor in COLUMN_FLOORS.items())


def _rejecting_client(message: str) -> OpenProjectClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/work_packages"
        error = {
            "_type": "Error",
            "errorIdentifier": "urn:openproject-org:api:v3:errors:InvalidQuery",
            "message": message,
        }
        return httpx.Response(400, json=error, request=request)

    return OpenProjectClient(make_settings(), transport=httpx.MockTransport(handler))


async def test_a_rejected_newer_column_names_the_release_it_needs() -> None:
    client = _rejecting_client("Can't sort by column: sprint")

    with pytest.raises(InvalidInputError) as exc_info:
        await client.work_package.list(sort_by=_validate_sort_by(["sprint"]))

    assert str(exc_info.value) == (
        "Can't sort by column: sprint If this instance is older than OpenProject 17.4, "
        "the sprint column is the cause: it requires 17.4 or newer."
    )
    await client.aclose()


async def test_a_rejection_with_several_newer_columns_names_every_release() -> None:
    client = _rejecting_client("Can't group by: observed_in_versions")

    with pytest.raises(InvalidInputError) as exc_info:
        await client.work_package.list(
            sort_by=_validate_sort_by(["project_phase"]), group_by=_validate_group_by("observed_in_versions")
        )

    assert str(exc_info.value) == (
        "Can't group by: observed_in_versions If this instance is older than OpenProject 16.1, "
        "the project_phase column is the cause: it requires 16.1 or newer. "
        "If this instance is older than OpenProject 17.9, the observed_in_versions column is the cause: "
        "it requires 17.9 or newer."
    )
    await client.aclose()


async def test_a_rejection_without_a_newer_column_keeps_the_server_message() -> None:
    client = _rejecting_client("Status Operator is not set to one of the allowed values.")

    with pytest.raises(InvalidInputError) as exc_info:
        await client.work_package.list(sort_by=_validate_sort_by(["status"]))

    assert str(exc_info.value) == "Status Operator is not set to one of the allowed values."
    await client.aclose()
