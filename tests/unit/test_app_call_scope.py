from __future__ import annotations

import asyncio

import pytest

from openproject_ce_mcp.app.call_scope import current_tool_call, tool_call
from openproject_ce_mcp.tools_runtime import _categorize_tool_errors


def test_there_is_no_call_outside_a_scope() -> None:
    assert current_tool_call() is None


def test_a_scope_names_its_call_and_each_scope_has_its_own_name() -> None:
    with tool_call() as first:
        assert current_tool_call() == first
    with tool_call() as second:
        assert second != first
    assert current_tool_call() is None


def test_a_scope_ends_when_the_body_raises() -> None:
    with pytest.raises(RuntimeError), tool_call():
        raise RuntimeError("boom")

    assert current_tool_call() is None


@pytest.mark.asyncio
async def test_concurrent_tasks_keep_their_own_call() -> None:
    async def body() -> tuple[int | None, int | None]:
        with tool_call() as own:
            await asyncio.sleep(0)
            return own, current_tool_call()

    results = await asyncio.gather(body(), body())

    assert all(own == seen for own, seen in results)
    assert results[0][0] != results[1][0]


@pytest.mark.asyncio
async def test_every_registered_tool_runs_inside_its_own_call() -> None:
    async def tool() -> int | None:
        return current_tool_call()

    wrapped = _categorize_tool_errors(tool)

    first, second = await wrapped(), await wrapped()

    assert first is not None
    assert second is not None
    assert first != second
