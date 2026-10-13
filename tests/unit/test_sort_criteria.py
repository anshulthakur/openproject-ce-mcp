from __future__ import annotations

import pytest

from openproject_ce_mcp.app.api_href import sort_by_path
from openproject_ce_mcp.models import SortCriterion
from openproject_ce_mcp.sort_criteria import parse_sort_by, parse_sort_criterion

_FORMAT_HINT = 'Use "field:direction" or "field-direction", e.g. "id:asc".'


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("id", SortCriterion("id", "asc")),
        (" id : DESC ", SortCriterion("id", "desc")),
        ("start_date-desc", SortCriterion("start_date", "desc")),
        ("dueDate-ASC", SortCriterion("dueDate", "asc")),
        ("cf_12:asc", SortCriterion("cf_12", "asc")),
    ],
)
def test_parse_sort_criterion_accepts_each_form(value: str, expected: SortCriterion) -> None:
    assert parse_sort_criterion(value, label="sort_by[0]") == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "sort_by[1] cannot be empty"),
        ("   ", "sort_by[1] cannot be empty"),
        (":asc", "sort_by[1]: field name cannot be empty"),
        ("-asc", "sort_by[1]: field name cannot be empty"),
        ("id:", f"sort_by[1]: direction must be 'asc' or 'desc', got ''. {_FORMAT_HINT}"),
        ("id-", f"sort_by[1]: direction must be 'asc' or 'desc', got ''. {_FORMAT_HINT}"),
        ("id:up", f"sort_by[1]: direction must be 'asc' or 'desc', got 'up'. {_FORMAT_HINT}"),
        (
            "status desc",
            "sort_by[1]: field name 'status desc' contains invalid characters "
            "(only alphanumeric, underscore, and dot allowed)",
        ),
        (
            "a/b:asc",
            "sort_by[1]: field name 'a/b' contains invalid characters (only alphanumeric, underscore, and dot allowed)",
        ),
        (
            "é:asc",
            "sort_by[1]: field name 'é' contains invalid characters (only alphanumeric, underscore, and dot allowed)",
        ),
    ],
)
def test_parse_sort_by_names_the_failing_item(value: str, message: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_sort_by(["id", value], field_name="sort_by")

    assert str(excinfo.value) == message


def test_parse_sort_by_keeps_an_empty_list_empty() -> None:
    assert parse_sort_by([], field_name="sort_by") == []


def test_sort_by_path_joins_field_and_direction_with_a_hyphen() -> None:
    assert sort_by_path(SortCriterion("dueDate", "desc")) == "queries/sort_bys/dueDate-desc"
