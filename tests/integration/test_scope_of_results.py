"""Results name only what the read allowlist covers.

A readable project can sit below, or work with, a project the allowlist does not cover. The
parent, the activity's project list and a write preview's links must not name that project.
"""

from __future__ import annotations

import uuid

import pytest

from openproject_ce_mcp.client import OpenProjectClient

from .conftest import disposable_project_identifier

pytestmark = pytest.mark.integration


async def _two_projects(everywhere: OpenProjectClient, project_refs: list[str]) -> tuple[str, str]:
    parent, child = disposable_project_identifier(), disposable_project_identifier()
    for identifier, parent_ref in ((parent, None), (child, parent)):
        created = await everywhere.project.create(
            name=f"[integration-test] {identifier}",
            identifier=identifier,
            confirm=True,
            **({"parent": parent_ref} if parent_ref else {}),
        )
        assert created.ready, created.validation_errors
    # Deleting a project deletes its subprojects; deleting the child as well would race that job.
    project_refs.append(parent)
    return parent, child


async def test_time_entry_activities_name_only_projects_the_read_scope_covers(
    test_project: str, project_refs: list[str], start_scoped_client
) -> None:
    everywhere = await start_scoped_client(read_projects=("*",), write_projects=("*",))
    other, _ = await _two_projects(everywhere, project_refs)
    scoped = await start_scoped_client(read_projects=(test_project,), write_projects=(test_project,))

    activities = await scoped.time_entry.list_activities()

    if not activities.results:
        pytest.skip("this instance lists no time entry activities")
    named = {name for activity in activities.results for name in activity.projects}
    assert not any(other in name for name in named)
    everyone = await everywhere.time_entry.list_activities()
    assert any(other in name or f"[integration-test] {other}" == name for a in everyone.results for name in a.projects)
