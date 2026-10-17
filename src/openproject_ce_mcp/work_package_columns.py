"""The work-package columns OpenProject sorts and groups by, and the release each needs.

A pure rule shared by the tool layer and `app/`, neither of which may import the other.
The names are OpenProject's own (its parser also accepts camelCase and the aliases noted
below). The sets are the union over the supported releases: a column an older instance
lacks is rejected by that instance, and `floors_used` names the release in the error.
"""

from __future__ import annotations

from collections.abc import Iterable

# assignee, estimated_time, remaining_time and percentage_done are OpenProject's
# aliases of assigned_to, estimated_hours, remaining_hours and done_ratio.
SORTABLE_FIELDS = frozenset(
    {
        "id",
        "project",
        "subject",
        "type",
        "status",
        "priority",
        "author",
        "assigned_to",
        "assignee",
        "responsible",
        "updated_at",
        "category",
        "version",
        "target_versions",
        "observed_in_versions",
        "start_date",
        "due_date",
        "estimated_hours",
        "estimated_time",
        "remaining_hours",
        "remaining_time",
        "done_ratio",
        "percentage_done",
        "created_at",
        "duration",
        "project_phase",
        "story_points",
        "position",
        "sprint",
        "backlog_bucket",
    }
)

# The columns with one database value per group; the id, text, dates, hours, duration,
# story_points and position sort but cannot be grouped by.
GROUPABLE_FIELDS = frozenset(
    {
        "project",
        "type",
        "status",
        "priority",
        "author",
        "assigned_to",
        "assignee",
        "responsible",
        "category",
        "version",
        "target_versions",
        "observed_in_versions",
        "done_ratio",
        "percentage_done",
        "project_phase",
        "sprint",
        "backlog_bucket",
    }
)

# Where a column first exists. sprint is sortable from 17.4 although writing a sprint
# is possible from 17.3: the query column came one release later. target_versions
# is `version` under its newer name (17.8 translates either name to the active one).
COLUMN_FLOORS = {
    "project_phase": "16.1",
    "sprint": "17.4",
    "backlog_bucket": "17.6",
    "target_versions": "17.8",
    "observed_in_versions": "17.9",
}


def floors_used(sort_fields: Iterable[str], group_field: str | None) -> list[tuple[str, str]]:
    """The (column, release) pairs a request uses, oldest release first."""
    used = {field for field in (*sort_fields, group_field) if field in COLUMN_FLOORS}
    return sorted(((field, COLUMN_FLOORS[field]) for field in used), key=lambda pair: _release_key(pair[1]))


def _release_key(release: str) -> tuple[int, ...]:
    return tuple(int(part) for part in release.split("."))


def describe_floors() -> str:
    return ", ".join(
        f"{field} {floor}+" for field, floor in sorted(COLUMN_FLOORS.items(), key=lambda p: _release_key(p[1]))
    )


def sort_by_description() -> str:
    fields = ", ".join(sorted(SORTABLE_FIELDS))
    return (
        'Sort criteria as "field:direction" or "field-direction" (e.g. ["status:desc", "priority-asc"]); '
        f"the direction defaults to asc. Fields: {fields}, or a custom field's cf_<id>. "
        f"Newer columns need an OpenProject release: {describe_floors()}; target_versions is version under its newer name. "
        "sprint and backlog_bucket also need the Backlogs module in a project where you may view sprints."
    )


def group_by_description() -> str:
    fields = ", ".join(sorted(GROUPABLE_FIELDS))
    return (
        f"One field to group the results by: {fields}, or a custom field's cf_<id>. "
        f"Newer columns need an OpenProject release: {describe_floors()}; target_versions is version under its newer name. "
        "sprint and backlog_bucket also need the Backlogs module in a project where you may view sprints."
    )
