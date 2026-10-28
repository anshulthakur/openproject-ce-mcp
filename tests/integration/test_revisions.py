"""Integration tests for work package revision reads.

OpenProject has no revision write endpoint; docker/test/seed.rb seeds a work package linked to one changeset. A
work package without a linked repository answers 200 with an empty collection, whether the repository module is
on or off.
"""

from __future__ import annotations

import pytest

from openproject_ce_mcp.client import OpenProjectClient

pytestmark = pytest.mark.integration


async def test_a_work_package_without_a_repository_has_no_revisions(
    client: OpenProjectClient, test_project: str, wp_ids: list[int]
) -> None:
    created = await client.work_package.create(
        project=test_project, type="Task", subject="[integration-test] revisions", confirm=True
    )
    assert created.ready, created.validation_errors
    wp_ids.append(created.work_package_id)

    result = await client.revision.list_for_work_package(created.work_package_id)

    assert result.count == 0
    assert result.results == []


async def _seeded_revision_work_package(client: OpenProjectClient, project: str) -> int:
    offset: int | None = 1
    while offset is not None:
        page = await client.work_package.list(project=project, limit=50, offset=offset)
        for wp in page.results:
            if wp.subject == "Seed revision work package":
                return wp.id
        offset = page.next_offset
    pytest.fail("the seeded revision work package is missing: re-run docker/test/up.sh to seed it")


async def test_a_linked_changeset_is_listed_with_untrusted_text_delimited(
    client: OpenProjectClient, test_project: str
) -> None:
    work_package = await _seeded_revision_work_package(client, test_project)

    result = await client.revision.list_for_work_package(work_package)

    assert result.count == 1
    revision = result.results[0]
    assert revision.formatted_identifier == "a1b2c3d4"
    # OpenProject renders the committer without the e-mail address.
    assert revision.author_name == "<user-content>Ada Lovelace</user-content>"
    assert revision.message == "<user-content>Seed commit</user-content>"
    assert revision.project is not None
    assert revision.created_at
