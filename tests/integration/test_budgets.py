"""Integration tests for project budget reads.

OpenProject's v3 API has no budget create endpoint; docker/test/seed.rb seeds
one budget into the test project.
"""

from __future__ import annotations

import pytest

from openproject_ce_mcp.client import OpenProjectClient

pytestmark = pytest.mark.integration


async def test_list_project_budgets(client: OpenProjectClient, test_project: str) -> None:
    result = await client.budget.list(test_project)

    assert result.count == len(result.results) > 0
    budget = result.results[0]
    assert budget.subject
    assert budget.project_id is not None
    assert budget.project
