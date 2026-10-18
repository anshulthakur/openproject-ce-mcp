"""A work package whose parent sits in a project the read scope does not cover.

The parent's id and display id carry the other project's identifier. Every result that shows a
parent leaves it out in that case, through the same bulk project check the hierarchy filter uses.

Functions only, in an underscore-prefixed module: every public class under app/services/ must be
named `*Service`/`*Resolver`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import TypeVar

from ...config import Settings
from ...models import WorkPackageDetail, WorkPackageSummary
from ..api_href import api_href
from ..policies.scope import scope_allows_all
from ..ports.work_package_ref import WorkPackageProjectAllowedBulkCheck
from ..ports.work_package_resolution import WorkPackageAllowedContext

ParentT = TypeVar("ParentT", WorkPackageSummary, WorkPackageDetail)


def parent_href(parent_id: int | None, *, api_prefix: str) -> str | None:
    return None if parent_id is None else api_href(f"work_packages/{parent_id}", api_prefix=api_prefix)


def without_parent_unless(item: ParentT, href: str | None, outcomes: Mapping[str, bool | Exception]) -> ParentT:
    """The item without its parent link when the check of `href` in `outcomes` says the parent's
    project is not covered; a failed check propagates."""
    if href is None:
        return item
    outcome = outcomes[href]
    if isinstance(outcome, Exception):
        raise outcome
    if outcome:
        return item
    return dataclasses.replace(item, parent_id=None, parent_display_id=None)


async def without_uncovered_parents(
    items: Sequence[ParentT],
    *,
    settings: Settings,
    api_prefix: str,
    project_allowed_bulk: WorkPackageProjectAllowedBulkCheck,
) -> list[ParentT]:
    """The items, each without a parent the read scope does not cover; one deduplicated bulk check
    for the whole page, none under `*`. A parent that is one of the items was admitted already and
    is not looked up again."""
    if scope_allows_all(settings.read_projects):
        return list(items)
    hrefs = {item.parent_id: parent_href(item.parent_id, api_prefix=api_prefix) for item in items}
    wanted = [href for href in hrefs.values() if href]
    if not wanted:
        return list(items)
    context = WorkPackageAllowedContext()
    for item in items:
        context.set(parent_href(item.id, api_prefix=api_prefix) or "", True)
    outcomes = await project_allowed_bulk(wanted, context=context)
    return [without_parent_unless(item, hrefs[item.parent_id], outcomes) for item in items]
