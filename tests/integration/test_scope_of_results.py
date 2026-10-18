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


async def test_a_project_does_not_name_a_parent_outside_the_read_scope(
    project_refs: list[str], start_scoped_client
) -> None:
    everywhere = await start_scoped_client(read_projects=("*",), write_projects=("*",))
    parent, child = await _two_projects(everywhere, project_refs)

    child_only = await start_scoped_client(read_projects=(child,), write_projects=(child,))
    project = await child_only.project.get(child)
    listed = next(row for row in (await child_only.project.list(search=child)).results if row.identifier == child)

    for result in (project, listed):
        assert (result.parent_id, result.parent_name) == (None, None)
    assert project.ancestors is None

    both = await start_scoped_client(read_projects=(parent, child), write_projects=(child,))
    assert (await both.project.get(child)).parent_name is not None


async def test_a_work_package_does_not_name_a_parent_in_a_project_outside_the_read_scope(
    project_refs: list[str], start_scoped_client
) -> None:
    everywhere = await start_scoped_client(read_projects=("*",), write_projects=("*",))
    parent_project, child_project = await _two_projects(everywhere, project_refs)
    secret = f"SECRET {uuid.uuid4().hex[:8]}"
    child_wp = await everywhere.work_package.create(project=child_project, type="Task", subject=secret, confirm=True)
    assert child_wp.ready, child_wp.validation_errors
    below = await everywhere.work_package.create(
        project=parent_project,
        type="Task",
        subject="[integration-test] below a foreign parent",
        parent_work_package_id=child_wp.work_package_id,
        confirm=True,
    )
    assert below.ready, below.validation_errors

    parent_only = await start_scoped_client(read_projects=(parent_project,), write_projects=(parent_project,))

    detail = await parent_only.work_package.get(below.work_package_id)
    assert (detail.parent_id, detail.parent_display_id) == (None, None)

    rows = await parent_only.work_package.list(project=parent_project)
    assert [(row.parent_id, row.parent_display_id) for row in rows.results] == [(None, None)]

    preview = await parent_only.work_package.update(
        work_package_id=below.work_package_id, subject="[integration-test] renamed", confirm=False
    )
    assert secret not in str(preview.payload)
    assert preview.payload["_links"]["parent"] == {"href": f"/api/v3/work_packages/{child_wp.work_package_id}"}

    both = await start_scoped_client(read_projects=(parent_project, child_project), write_projects=(parent_project,))
    assert (await both.work_package.get(below.work_package_id)).parent_id == child_wp.work_package_id


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
