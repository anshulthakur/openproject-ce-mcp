"""Projects created after the server started, by another client.

A client scans the project list once at startup; a project that appears later
is only known through the responses that link it. These tests start the scoped
client first and create the projects with a second, unrestricted one.
"""

from __future__ import annotations

import pytest

from openproject_ce_mcp.client import OpenProjectClient, PermissionDeniedError

from .conftest import disposable_project_identifier

pytestmark = pytest.mark.integration


def _outside_the_it_pattern(identifier: str) -> str:
    # Keeps the instance's identifier casing (see disposable_project_identifier).
    return ("ZZ" if identifier[:2].isupper() else "zz") + identifier[2:]


async def _project_with_a_work_package(
    unrestricted: OpenProjectClient, identifier: str, project_refs: list[str]
) -> int:
    created = await unrestricted.project.create(
        name=f"[integration-test] {identifier}", identifier=identifier, confirm=True
    )
    assert created.ready, created.validation_errors
    project_refs.append(identifier)
    work_package = await unrestricted.work_package.create(
        project=identifier, type="Task", subject="[integration-test] project directory", confirm=True
    )
    assert work_package.ready, work_package.validation_errors
    return work_package.work_package_id


async def _all_listed_ids(scoped: OpenProjectClient) -> set[int]:
    listed: set[int] = set()
    offset: int | None = 1
    while offset is not None:
        page = await scoped.work_package.list(offset=offset, limit=scoped.settings.max_results)
        listed.update(work_package.id for work_package in page.results)
        offset = page.next_offset
    return listed


async def test_a_project_created_by_another_client_is_read_and_listed_by_its_allowlist_pattern(
    start_scoped_client, project_refs: list[str]
) -> None:
    scoped = await start_scoped_client(read_projects=("IT*",), write_projects=("IT*",))
    unrestricted = await start_scoped_client(read_projects=("*",), write_projects=("*",))

    inside = disposable_project_identifier()
    inside_work_package = await _project_with_a_work_package(unrestricted, inside, project_refs)
    outside_work_package = await _project_with_a_work_package(
        unrestricted, _outside_the_it_pattern(disposable_project_identifier()), project_refs
    )

    read_back = await scoped.work_package.get(inside_work_package)
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        await scoped.work_package.get(outside_work_package)
    listed_ids = await _all_listed_ids(scoped)

    assert read_back.id == inside_work_package
    assert inside_work_package in listed_ids
    assert outside_work_package not in listed_ids


async def _renamed_project_with_content(
    unrestricted: OpenProjectClient, project_refs: list[str]
) -> tuple[int, str, str, int, int]:
    """A throwaway project with a work package and a version; returns its id,
    former and current identifier, the work package id and the version id. The
    rename happens later, through `rename`."""
    former = disposable_project_identifier()
    current = disposable_project_identifier()
    # The name must match neither identifier, or the link title alone would decide.
    created = await unrestricted.project.create(
        name="[integration-test] renamed while running", identifier=former, confirm=True
    )
    assert created.ready, created.validation_errors
    assert created.project_id is not None
    project_refs.append(str(created.project_id))
    work_package = await unrestricted.work_package.create(
        project=former, type="Task", subject="[integration-test] renamed project content", confirm=True
    )
    assert work_package.ready, work_package.validation_errors
    version = await unrestricted.version.create(project=former, name="[integration-test] renamed", confirm=True)
    assert version.ready, version.validation_errors
    assert version.version_id is not None
    return created.project_id, former, current, work_package.work_package_id, version.version_id


async def _rename(unrestricted: OpenProjectClient, project_id: int, identifier: str) -> None:
    renamed = await unrestricted.project.update(project_ref=str(project_id), identifier=identifier, confirm=True)
    assert renamed.ready, renamed.validation_errors


async def _all_listed_version_ids(scoped: OpenProjectClient) -> set[int]:
    listed: set[int] = set()
    offset: int | None = 1
    while offset is not None:
        page = await scoped.version.list(offset=offset, limit=scoped.settings.max_results)
        listed.update(version.id for version in page.results)
        offset = page.next_offset
    return listed


async def test_content_of_a_project_renamed_while_the_server_runs_is_denied_by_its_former_identifier(
    start_scoped_client, project_refs: list[str]
) -> None:
    unrestricted = await start_scoped_client(read_projects=("*",), write_projects=("*",))
    project_id, former, current, work_package_id, version_id = await _renamed_project_with_content(
        unrestricted, project_refs
    )
    by_former = await start_scoped_client(read_projects=(former,), write_projects=(former,))
    assert version_id in await _all_listed_version_ids(by_former)

    await _rename(unrestricted, project_id, current)

    # A listed version only links its project; a single work package embeds it.
    assert version_id not in await _all_listed_version_ids(by_former)
    with pytest.raises(PermissionDeniedError, match="OPENPROJECT_READ_PROJECTS"):
        await by_former.work_package.get(work_package_id)

    by_current = await start_scoped_client(read_projects=(current,), write_projects=(current,))
    assert (await by_current.work_package.get(work_package_id)).id == work_package_id


async def test_work_package_counts_and_sums_leave_out_a_project_renamed_while_the_server_runs(
    start_scoped_client, project_refs: list[str], test_project: str
) -> None:
    unrestricted = await start_scoped_client(read_projects=("*",), write_projects=("*",))
    project_id, former, current, work_package_id, _ = await _renamed_project_with_content(unrestricted, project_refs)
    scoped = await start_scoped_client(read_projects=(former, test_project), write_projects=())
    before = await scoped.work_package.list(limit=1, include_sums=True)
    in_test_project = await unrestricted.work_package.list(project=test_project, limit=1, include_sums=True)
    assert before.total == in_test_project.total + 1

    await _rename(unrestricted, project_id, current)

    after = await scoped.work_package.list(limit=1, include_sums=True)
    assert after.total == in_test_project.total
    assert after.total_sums == in_test_project.total_sums
    assert work_package_id not in await _all_listed_ids(scoped)
