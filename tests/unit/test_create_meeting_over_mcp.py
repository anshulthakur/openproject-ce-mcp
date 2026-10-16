"""create_meeting with state or notify, from the MCP call to the HTTP requests:
the rejection reaches the agent as a validation error and nothing is sent."""

from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from _client_test_helpers import make_settings, started_client
from mcp import types
from mcp.client import Client

import openproject_ce_mcp.tools_runtime as tools_runtime
from openproject_ce_mcp import tools, tools_meetings
from openproject_ce_mcp.strict_mcpserver import StrictMCPServer


class _Recorder:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")


async def _call(recorder: _Recorder, arguments: dict) -> types.CallToolResult:
    settings = dataclasses.replace(make_settings(), enable_meeting_read=True, enable_meeting_write=True)

    @asynccontextmanager
    async def lifespan(_):
        client = await started_client(settings, recorder.handler, [(6, "demo", "Demo")])
        try:
            yield SimpleNamespace(client=client)
        finally:
            await client.aclose()

    server = StrictMCPServer("test", lifespan=lifespan)
    tools_runtime.register_selected_tools(
        server, names=[tools_meetings.create_meeting.__name__], hide_active=False, annotations=tools.TOOL_ANNOTATIONS
    )
    async with Client(server, mode="legacy") as client:
        recorder.requests.clear()
        return await client.call_tool("create_meeting", arguments)


def _text(result: types.CallToolResult) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


@pytest.mark.parametrize("extra", [{"state": "open"}, {"notify": True}])
async def test_state_or_notify_is_rejected_as_a_validation_error_without_a_request(extra: dict) -> None:
    recorder = _Recorder()

    result = await _call(recorder, {"project": "demo", "title": "Weekly", "confirm": True, **extra})

    assert result.is_error is True
    assert "[VALIDATION_FAILED] create_meeting does not apply state or notify" in _text(result)
    assert recorder.requests == []
