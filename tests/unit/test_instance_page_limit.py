"""The instance's maximum API page size is read once at startup and caps the configured sizes."""

from __future__ import annotations

import dataclasses
import logging

import httpx
import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.client import with_instance_page_limit


def _transport(reported: object, seen: list[httpx.Request] | None = None, *, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = {"_type": "Collection", "total": 3, "_embedded": {"elements": []}}
        if reported is not None:
            body["pageSize"] = reported
        return httpx.Response(status, json=body, request=request)

    return httpx.MockTransport(handler)


def _settings(**changes):
    return dataclasses.replace(make_settings(), max_page_size=50, default_page_size=20, max_results=100, **changes)


@pytest.mark.asyncio
async def test_a_lower_instance_maximum_caps_both_page_sizes(caplog: pytest.LogCaptureFixture) -> None:
    seen: list[httpx.Request] = []

    with caplog.at_level(logging.WARNING):
        settings = await with_instance_page_limit(_settings(), transport=_transport(25, seen))

    assert (settings.max_page_size, settings.default_page_size) == (25, 20)
    assert len(seen) == 1
    assert seen[0].url.params["pageSize"] == "50"
    assert seen[0].url.params["offset"] == "1000000"
    assert "limits API pages to 25" in caplog.text


@pytest.mark.asyncio
async def test_the_default_page_size_never_exceeds_the_lowered_maximum() -> None:
    settings = await with_instance_page_limit(_settings(), transport=_transport(10))

    assert (settings.max_page_size, settings.default_page_size) == (10, 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("reported", [50, 1000, None, 0, "20"])
async def test_any_other_report_leaves_the_settings_unchanged(reported: object) -> None:
    original = _settings()

    assert await with_instance_page_limit(original, transport=_transport(reported)) is original


@pytest.mark.asyncio
async def test_a_failed_probe_leaves_the_settings_unchanged_and_says_so(caplog: pytest.LogCaptureFixture) -> None:
    original = _settings()

    with caplog.at_level(logging.WARNING):
        result = await with_instance_page_limit(original, transport=_transport(None, status=500))

    assert result is original
    assert "could not be read" in caplog.text


@pytest.mark.asyncio
async def test_the_server_runs_with_the_capped_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from openproject_ce_mcp import server

    built: list[object] = []

    class _Client:
        def __init__(self, settings) -> None:
            built.append(settings)

        async def initialize(self) -> None: ...

    async def capped(settings):
        return dataclasses.replace(settings, max_page_size=7)

    monkeypatch.setattr(server, "OpenProjectClient", _Client)
    monkeypatch.setattr(server, "with_instance_page_limit", capped)

    context = await server.open_context(_settings())

    assert context.settings.max_page_size == 7
    assert built == [context.settings]
