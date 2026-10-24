from __future__ import annotations

import pytest

from openproject_ce_mcp.app.errors import InvalidInputError, NotFoundError, OpenProjectServerError
from openproject_ce_mcp.app.version_gate import call_query_version_gated, call_version_gated


@pytest.mark.asyncio
async def test_call_version_gated_returns_the_call_result_on_success() -> None:
    async def call() -> str:
        return "ok"

    assert await call_version_gated(call, feature="Meetings", floor="17.4") == "ok"


@pytest.mark.asyncio
async def test_call_version_gated_translates_not_found_into_a_version_hint() -> None:
    async def call() -> None:
        raise NotFoundError("boom")

    with pytest.raises(NotFoundError) as raised:
        await call_version_gated(call, feature="Meetings", floor="17.4")

    assert str(raised.value) == (
        "Meetings: not found, or not available on this instance (it requires OpenProject 17.4 or newer)."
    )
    # A 404 on a current instance is usually a missing resource: the message must not say otherwise.
    assert "older" not in str(raised.value)


@pytest.mark.asyncio
async def test_call_version_gated_chains_the_original_exception() -> None:
    original = NotFoundError("boom")

    async def call() -> None:
        raise original

    with pytest.raises(NotFoundError) as exc_info:
        await call_version_gated(call, feature="Meetings", floor="17.4")
    assert exc_info.value.__cause__ is original


@pytest.mark.asyncio
async def test_call_version_gated_only_translates_not_found_error() -> None:
    async def call() -> None:
        raise OpenProjectServerError("something else")

    with pytest.raises(OpenProjectServerError, match="something else"):
        await call_version_gated(call, feature="Meetings", floor="17.4")


@pytest.mark.asyncio
async def test_call_query_version_gated_returns_the_call_result_on_success() -> None:
    async def call() -> str:
        return "ok"

    assert await call_query_version_gated(call, feature="version_status", floor="16.4") == "ok"


@pytest.mark.asyncio
async def test_call_query_version_gated_keeps_the_server_reason_and_adds_the_floor() -> None:
    original = InvalidInputError("Version Operator is not set to one of the allowed values.")

    async def call() -> None:
        raise original

    with pytest.raises(InvalidInputError) as exc_info:
        await call_query_version_gated(call, feature="version_status", floor="16.4")
    assert str(exc_info.value) == (
        "Version Operator is not set to one of the allowed values. If this instance is older than "
        "OpenProject 16.4, version_status is the cause: it requires 16.4 or newer."
    )
    assert exc_info.value.__cause__ is original


@pytest.mark.asyncio
async def test_call_query_version_gated_only_translates_invalid_input_error() -> None:
    original = NotFoundError("boom")

    async def call() -> None:
        raise original

    with pytest.raises(NotFoundError) as exc_info:
        await call_query_version_gated(call, feature="version_status", floor="16.4")
    assert exc_info.value is original
