"""A project reference is searched as literal text: OpenProject's name_and_identifier
filter puts the value into LIKE '%value%' unescaped, so `_` and `%` would be wildcards."""

from __future__ import annotations

import json

import httpx
import pytest
from _client_test_helpers import make_settings

from openproject_ce_mcp.client import NotFoundError, OpenProjectClient


def _client(captured: list[list[dict]]) -> OpenProjectClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/v3/projects":
            return httpx.Response(404, json={"message": "not found"}, request=request)
        captured.append(json.loads(request.url.params.get("filters", "[]")))
        return httpx.Response(200, json={"_embedded": {"elements": []}, "total": 0}, request=request)

    return OpenProjectClient(make_settings(), transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "search, sent",
    [
        ("plain", "plain"),
        ("a_b", r"a\_b"),
        ("100%", r"100\%"),
        (r"back\slash", r"back\\slash"),
        (r"a_b%c\d", r"a\_b\%c\\d"),
    ],
)
async def test_list_projects_sends_the_search_text_with_like_wildcards_escaped(search: str, sent: str) -> None:
    captured: list[list[dict]] = []
    client = _client(captured)
    try:
        await client.project.list(search=search)
    finally:
        await client.aclose()

    (filters,) = captured
    assert filters == [{"name_and_identifier": {"operator": "~", "values": [sent]}}]


async def test_resolving_a_project_by_name_searches_with_the_wildcards_escaped() -> None:
    captured: list[list[dict]] = []
    client = _client(captured)
    try:
        with pytest.raises(NotFoundError, match="a_b"):
            await client.project.get("a_b")
    finally:
        await client.aclose()

    assert any(
        f == {"name_and_identifier": {"operator": "~", "values": [r"a\_b"]}} for filters in captured for f in filters
    )
