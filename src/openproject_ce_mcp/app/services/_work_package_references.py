"""Which versions and sprints a work package result may name.

A work package of a covered project can carry a version or sprint shared into it from a project the
read scope does not cover. The decision is made here, once per call, and handed to the adapters as
`VisibleReferences`: this is the only module that builds one, so a result cannot be presented
without it.

Functions only, in an underscore-prefixed module: every public class under app/services/ must be
named `*Service`/`*Resolver`.
"""

from __future__ import annotations

from collections.abc import Container, Iterable, Mapping, Sequence
from typing import Any

from ...config import Settings
from ...models import WorkPackageGroupSums
from ..policies import hidden_fields
from ..policies.scope import scope_allows_all
from ..ports.scoped_reference import ScopedReference, ScopedReferencesAllowedBulkCheck, VisibleReferences
from ..ports.work_package_api import WorkPackageGroupRecord, WorkPackageRecord

# The columns whose group label is the name of a version or sprint.
_REFERENCE_COLUMNS = frozenset({"version", "target_versions", "observed_in_versions", "sprint"})
# Bucket names carry no link to check.
_UNCHECKABLE_COLUMNS = frozenset({"backlog_bucket"})
# version and target_versions read and write the same data: hiding one hides both.
_VERSION_FIELDS = ("version", "target_versions")


def _field_shown(field: str, *, settings: Settings) -> bool:
    if field.startswith("customField"):
        return not (
            hidden_fields.field_hidden("work_package", "custom_fields", settings=settings)
            or hidden_fields.custom_field_hidden(field, field, settings=settings)
        )
    names = _VERSION_FIELDS if field in _VERSION_FIELDS else (field,)
    return not any(hidden_fields.field_hidden("work_package", name, settings=settings) for name in names)


async def visible_references(
    *,
    records: Sequence[WorkPackageRecord] = (),
    groups: Sequence[WorkPackageGroupRecord] = (),
    settings: Settings,
    check: ScopedReferencesAllowedBulkCheck,
    fields: Container[str] | None = None,
) -> VisibleReferences:
    """The references the results built from `records` and `groups` may name. Everything under `*`;
    otherwise one deduplicated check for the references of the fields that are shown (and, when
    given, among `fields`), which fails as a whole if any check fails."""
    if scope_allows_all(settings.read_projects):
        return VisibleReferences.everything()
    wanted: dict[ScopedReference, None] = {}
    seeds: dict[ScopedReference, Mapping[str, Any]] = {}
    for record in records:
        for field, references in record.references.items():
            if (fields is None or field in fields) and _field_shown(field, settings=settings):
                wanted.update(dict.fromkeys(references))
        seeds.update(record.seeds)
    for group in groups:
        wanted.update(dict.fromkeys(group.references))
    outcomes = await check(wanted, seeds=seeds) if wanted else {}
    visible: list[ScopedReference] = []
    for reference in wanted:
        outcome = outcomes[reference]
        if isinstance(outcome, Exception):
            raise outcome
        if outcome:
            visible.append(reference)
    return VisibleReferences.only(visible)


def groups_for_result(
    groups: Iterable[WorkPackageGroupRecord], *, group_by: str | None, visible: VisibleReferences
) -> list[WorkPackageGroupSums] | None:
    """The groups, or None when any group label names a version or sprint the result may not name.
    Dropping only that group would leave counts and sums that do not add up, and merging it into
    another would still reveal that it exists."""
    result: list[WorkPackageGroupSums] = []
    for group in groups:
        if not all(visible.contains(reference) for reference in group.references):
            return None
        if group.value is not None and not group.references and group_by in _REFERENCE_COLUMNS | _UNCHECKABLE_COLUMNS:
            return None
        result.append(WorkPackageGroupSums(value=group.value, count=group.count, sums=group.sums))
    return result


# The link a write sets -> the result fields that show what it replaces.
_WRITTEN_LINK_FIELDS = {
    "version": ("version", "target_versions"),
    "targetVersions": ("version", "target_versions"),
    "sprint": ("sprint",),
}


async def hidden_references_replaced(
    record: WorkPackageRecord,
    written_links: Iterable[str],
    *,
    settings: Settings,
    check: ScopedReferencesAllowedBulkCheck,
) -> int:
    """How many versions and sprints a write that sets `written_links` would remove from `record`
    although a result may not name them, so the caller cannot know they are there. A custom field
    link is its own result field."""
    written = {field for link in written_links for field in _WRITTEN_LINK_FIELDS.get(link, (link,))}
    visible = await visible_references(records=[record], settings=settings, check=check, fields=written)
    replaced = {
        reference
        for field, references in record.references.items()
        if field in written and _field_shown(field, settings=settings)
        for reference in references
    }
    return sum(not visible.contains(reference) for reference in replaced)
