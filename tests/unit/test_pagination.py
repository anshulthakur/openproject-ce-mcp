from __future__ import annotations

import pytest

from openproject_ce_mcp.app.pagination import (
    fetch_bounded_and_paginate,
    paginate_all,
    scan_and_paginate,
    scan_records_and_paginate,
)


@pytest.mark.asyncio
async def test_scan_and_paginate_stops_after_limit_plus_one_allowed_matches() -> None:
    """Unlike paginate_all, this must NOT walk the entire
    collection -- only enough pages to confirm limit+1 allowed matches (or
    genuine exhaustion)."""
    calls: list[int] = []

    async def fetch_page(offset: int, page_size: int) -> dict:
        calls.append(offset)
        pages = {
            1: [{"id": 1}, {"id": 2}],
            2: [{"id": 3}, {"id": 4}],
            3: [{"id": 5}, {"id": 6}],
        }
        elements = pages.get(offset, [])
        return {"_embedded": {"elements": elements}}

    async def item_allowed(item: dict) -> bool:
        return True

    results, truncated = await scan_and_paginate(
        fetch_page=fetch_page, item_allowed=item_allowed, server_page_size=2, offset=1, limit=2
    )

    assert [r["id"] for r in results] == [1, 2]
    assert truncated is True
    # limit=2 needs limit+1=3 confirmed matches before it can stop -- page 1
    # gives 2, page 2's first item is the 3rd -- must not walk page 3.
    assert calls == [1, 2]


@pytest.mark.asyncio
async def test_scan_and_paginate_not_truncated_when_exactly_limit_matches_exist() -> None:
    async def fetch_page(offset: int, page_size: int) -> dict:
        if offset == 1:
            return {"total": 1, "_embedded": {"elements": [{"id": 1}]}}
        raise AssertionError(f"unexpected offset {offset}")

    async def item_allowed(item: dict) -> bool:
        return True

    results, truncated = await scan_and_paginate(
        fetch_page=fetch_page, item_allowed=item_allowed, server_page_size=2, offset=1, limit=1
    )

    assert [r["id"] for r in results] == [1]
    assert truncated is False


@pytest.mark.asyncio
async def test_scan_and_paginate_does_not_evaluate_item_allowed_past_the_limit_plus_one_match() -> None:
    """Efficiency regression: item_allowed must not be called for items
    AFTER the limit+1-th allowed match is found on a single page -- an
    earlier draft collected the whole page's allowed subset via a list
    comprehension before slicing, which called item_allowed on every raw
    element regardless of where the limit+1 cutoff fell."""
    checked_ids: list[int] = []

    async def fetch_page(offset: int, page_size: int) -> dict:
        return {"_embedded": {"elements": [{"id": i} for i in range(1, 6)]}}  # 5 raw elements, one page

    async def item_allowed(item: dict) -> bool:
        checked_ids.append(item["id"])
        return True

    results, truncated = await scan_and_paginate(
        fetch_page=fetch_page, item_allowed=item_allowed, server_page_size=5, offset=1, limit=1
    )

    assert [r["id"] for r in results] == [1]
    assert truncated is True
    # limit+1=2 confirmed matches is enough to stop -- ids 3/4/5 must never
    # be passed to item_allowed.
    assert checked_ids == [1, 2]


@pytest.mark.asyncio
async def test_scan_records_and_paginate_stops_after_limit_plus_one_allowed_matches() -> None:
    calls: list[int] = []

    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        calls.append(offset)
        pages = {1: [1, 2], 2: [3, 4], 3: [5, 6]}
        return pages.get(offset, []), 999

    results, truncated = await scan_records_and_paginate(
        fetch_page, item_allowed=lambda item: True, server_page_size=2, offset=1, limit=2, key=lambda item: item
    )

    assert results == [1, 2]
    assert truncated is True
    assert calls == [1, 2]


@pytest.mark.asyncio
async def test_scan_records_and_paginate_not_truncated_when_exactly_limit_matches_exist() -> None:
    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        if offset == 1:
            return [1], 1
        raise AssertionError(f"unexpected offset {offset}")

    results, truncated = await scan_records_and_paginate(
        fetch_page, item_allowed=lambda item: True, server_page_size=2, offset=1, limit=1, key=lambda item: item
    )

    assert results == [1]
    assert truncated is False


@pytest.mark.asyncio
async def test_scan_records_and_paginate_does_not_evaluate_item_allowed_past_the_limit_plus_one_match() -> None:
    """Same efficiency regression as scan_and_paginate's equivalent test,
    for the already-normalized-record variant."""
    checked: list[int] = []

    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        return [1, 2, 3, 4, 5], 999  # 5 records, one page

    def item_allowed(item: int) -> bool:
        checked.append(item)
        return True

    results, truncated = await scan_records_and_paginate(
        fetch_page, item_allowed=item_allowed, server_page_size=5, offset=1, limit=1, key=lambda item: item
    )

    assert results == [1]
    assert truncated is True
    assert checked == [1, 2]


ELEMENTS = [{"id": i} for i in range(1, 8)]


def _clamping_server(maximum: int, *, with_total: bool = True):
    """Serves ELEMENTS but cuts any requested page size to `maximum`, as OpenProject does."""
    requests: list[tuple[int, int]] = []

    async def fetch_page(offset: int, page_size: int) -> dict:
        requests.append((offset, page_size))
        start = (offset - 1) * maximum
        page = ELEMENTS[start : start + maximum]
        payload: dict = {"_embedded": {"elements": page}}
        if with_total:
            payload["total"] = len(ELEMENTS)
        return payload

    return fetch_page, requests


async def _allowed(item: dict) -> bool:
    return True


@pytest.mark.asyncio
async def test_a_server_that_cuts_the_page_size_is_still_read_to_its_end_by_fetch_bounded_and_paginate() -> None:
    fetch_page, requests = _clamping_server(maximum=2)

    results, total, next_offset, truncated = await fetch_bounded_and_paginate(
        fetch_page=fetch_page, normalize=lambda raw: raw["id"], server_page_size=50, offset=1, limit=100
    )

    assert (results, truncated, next_offset) == ([1, 2, 3, 4, 5, 6, 7], False, None)
    assert [offset for offset, _ in requests] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_a_server_that_cuts_the_page_size_is_still_read_to_its_end_by_scan_and_paginate() -> None:
    fetch_page, requests = _clamping_server(maximum=3)

    results, truncated = await scan_and_paginate(
        fetch_page=fetch_page, item_allowed=_allowed, server_page_size=50, offset=1, limit=100
    )

    assert ([r["id"] for r in results], truncated) == ([1, 2, 3, 4, 5, 6, 7], False)
    assert [offset for offset, _ in requests] == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_server_that_cuts_the_page_size_is_still_read_to_its_end_by_scan_records_and_paginate() -> None:
    clamped, requests = _clamping_server(maximum=2)

    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        payload = await clamped(offset, page_size)
        return [e["id"] for e in payload["_embedded"]["elements"]], payload["total"]

    results, truncated = await scan_records_and_paginate(
        fetch_page, item_allowed=lambda item: True, server_page_size=50, offset=1, limit=100, key=lambda item: item
    )

    assert (results, truncated) == ([1, 2, 3, 4, 5, 6, 7], False)
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_a_collection_without_a_total_is_read_until_an_empty_page() -> None:
    fetch_page, requests = _clamping_server(maximum=3, with_total=False)

    results, truncated = await scan_and_paginate(
        fetch_page=fetch_page, item_allowed=_allowed, server_page_size=50, offset=1, limit=100
    )

    assert ([r["id"] for r in results], truncated) == ([1, 2, 3, 4, 5, 6, 7], False)
    assert [offset for offset, _ in requests] == [1, 2, 3, 4]


@pytest.mark.parametrize(
    ("total", "fetched", "expected"), [(7, 7, True), (7, 8, True), (7, 6, False), (None, 100, False), ("7", 7, False)]
)
def test_a_collection_is_exhausted_when_the_fetched_elements_reach_its_total(total, fetched, expected) -> None:
    from openproject_ce_mcp.app.pagination import collection_exhausted

    assert collection_exhausted(total, fetched) is expected


@pytest.mark.asyncio
async def test_paginate_all_collects_a_single_page() -> None:
    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        assert (offset, page_size) == (1, 10)
        return [1, 2, 3], 3

    result = await paginate_all(fetch_page, page_size=10)

    assert result == [1, 2, 3]


@pytest.mark.asyncio
async def test_paginate_all_walks_multiple_pages_until_exhausted() -> None:
    pages = {1: (["a", "b"], 5), 2: (["c", "d"], 5), 3: (["e"], 5)}
    calls: list[tuple[int, int]] = []

    async def fetch_page(offset: int, page_size: int) -> tuple[list[str], int]:
        calls.append((offset, page_size))
        return pages[offset]

    result = await paginate_all(fetch_page, page_size=2)

    assert result == ["a", "b", "c", "d", "e"]
    assert calls == [(1, 2), (2, 2), (3, 2)]


@pytest.mark.asyncio
async def test_paginate_all_returns_empty_list_when_no_items() -> None:
    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        return [], 0

    result = await paginate_all(fetch_page, page_size=10)

    assert result == []


@pytest.mark.asyncio
async def test_scan_records_bulk_outcomes_filter_and_raise_only_where_reached() -> None:
    pages = {1: ([1, 2, 3, 4], 4)}
    bulk_calls: list[list[int]] = []

    async def fetch(offset: int, page_size: int):
        return pages.get(offset, ([], 4))

    async def bulk(items: list[int]) -> list[bool | Exception]:
        bulk_calls.append(items)
        return [True, False, True, RuntimeError("never reached")]

    results, truncated = await scan_records_and_paginate(
        fetch, item_allowed_bulk=bulk, server_page_size=10, offset=1, limit=1
    )

    assert results == [1]
    assert truncated is True
    assert bulk_calls == [[1, 2, 3, 4]]


@pytest.mark.asyncio
async def test_scan_records_bulk_outcome_exception_is_raised_when_reached() -> None:
    async def fetch(offset: int, page_size: int):
        return ([1, 2], 2) if offset == 1 else ([], 2)

    async def bulk(items: list[int]) -> list[bool | Exception]:
        return [True, RuntimeError("reached")]

    with pytest.raises(RuntimeError, match="reached"):
        await scan_records_and_paginate(fetch, item_allowed_bulk=bulk, server_page_size=10, offset=1, limit=5)


@pytest.mark.asyncio
async def test_scan_records_without_a_filter_scans_unfiltered() -> None:
    async def fetch(offset: int, page_size: int):
        return ([1, 2, 3], 3) if offset == 1 else ([], 3)

    results, truncated = await scan_records_and_paginate(fetch, server_page_size=10, offset=1, limit=5)

    assert results == [1, 2, 3]
    assert truncated is False


def test_page_is_last_uses_the_page_size_the_server_reports() -> None:
    from openproject_ce_mcp.app.pagination import page_is_last

    # asked for 100, the server cut it to 20: page 2 of 100 elements is not the last one
    assert page_is_last({"pageSize": 20}, offset=2, requested_page_size=100, total=100) is False
    assert page_is_last({"pageSize": 20}, offset=5, requested_page_size=100, total=100) is True


@pytest.mark.parametrize("payload", [{}, {"pageSize": None}, {"pageSize": 0}, {"pageSize": "20"}])
def test_page_is_last_falls_back_to_the_requested_size_without_a_usable_report(payload: dict) -> None:
    from openproject_ce_mcp.app.pagination import page_is_last

    assert page_is_last(payload, offset=1, requested_page_size=20, total=21) is False
    assert page_is_last(payload, offset=2, requested_page_size=20, total=21) is True


@pytest.mark.asyncio
async def test_a_server_that_cuts_the_page_size_is_still_read_to_its_end_by_paginate_all() -> None:
    clamped, requests = _clamping_server(maximum=2)

    async def fetch_page(offset: int, page_size: int) -> tuple[list[int], int]:
        payload = await clamped(offset, page_size)
        return [e["id"] for e in payload["_embedded"]["elements"]], payload["total"]

    items = await paginate_all(fetch_page, page_size=50, key=lambda item: item)

    assert items == [1, 2, 3, 4, 5, 6, 7]
    assert len(requests) == 4
