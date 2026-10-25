from __future__ import annotations

import asyncio

import pytest

from openproject_ce_mcp.app.caches import CachedValue, LoadingCache, TtlCache


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_value_is_remembered_until_it_expires() -> None:
    clock = _Clock()
    cache: TtlCache[str, int] = TtlCache(ttl_seconds=10, max_entries=5, clock=clock)

    cache.put("a", 1)
    clock.now = 10
    assert cache.get("a") == (1,)
    clock.now = 10.5
    assert cache.get("a") is None


def test_a_remembered_none_is_not_a_miss() -> None:
    cache: TtlCache[str, str | None] = TtlCache(ttl_seconds=10, max_entries=5)

    cache.put("gone", None)

    assert cache.get("gone") == (None,)
    assert cache.get("never seen") is None


def test_the_oldest_unused_entry_leaves_first_and_a_read_renews_an_entry() -> None:
    cache: TtlCache[str, int] = TtlCache(ttl_seconds=10, max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")

    cache.put("c", 3)

    assert (cache.get("a"), cache.get("b"), cache.get("c")) == ((1,), None, (3,))
    assert len(cache) == 2


def test_putting_a_key_again_replaces_the_value_and_restarts_its_time() -> None:
    clock = _Clock()
    cache: TtlCache[str, int] = TtlCache(ttl_seconds=10, max_entries=5, clock=clock)
    cache.put("a", 1)
    clock.now = 8
    cache.put("a", 2)
    clock.now = 15

    assert cache.get("a") == (2,)


class _Loader:
    def __init__(self, *values: object) -> None:
        self.values = list(values)
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        await asyncio.sleep(0)
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_a_loaded_value_is_remembered_until_it_expires() -> None:
    clock = _Clock()
    cache: LoadingCache[str, int] = LoadingCache(ttl_seconds=10, max_entries=5, clock=clock)
    load = _Loader(1, 2)

    assert await cache.get("a", load) == 1
    assert await cache.get("a", load) == 1
    clock.now = 11
    assert await cache.get("a", load) == 2
    assert load.calls == 2


@pytest.mark.asyncio
async def test_callers_asking_while_a_load_is_in_flight_share_it() -> None:
    cache: LoadingCache[str, int] = LoadingCache(max_entries=5)
    load = _Loader(7)

    results = await asyncio.gather(*(cache.get("a", load) for _ in range(4)))

    assert results == [7, 7, 7, 7]
    assert load.calls == 1
    assert cache.loading == 0


@pytest.mark.asyncio
async def test_a_failed_load_reaches_every_waiter_and_is_not_remembered() -> None:
    cache: LoadingCache[str, int] = LoadingCache(max_entries=5)
    load = _Loader(RuntimeError("down"), 3)

    first = await asyncio.gather(cache.get("a", load), cache.get("a", load), return_exceptions=True)

    assert [type(item) for item in first] == [RuntimeError, RuntimeError]
    assert load.calls == 1
    assert len(cache) == 0
    assert await cache.get("a", load) == 3


@pytest.mark.asyncio
async def test_a_cancelled_waiter_neither_cancels_the_load_nor_fails_the_others() -> None:
    cache: LoadingCache[str, int] = LoadingCache(max_entries=5)
    load = _Loader(5)
    cancelled = asyncio.create_task(cache.get("a", load))
    await asyncio.sleep(0)
    survivor = asyncio.create_task(cache.get("a", load))
    await asyncio.sleep(0)
    cancelled.cancel()

    assert await survivor == 5
    assert load.calls == 1


@pytest.mark.asyncio
async def test_no_more_than_the_allowed_number_of_loads_run_at_once() -> None:
    cache: LoadingCache[int, int] = LoadingCache(max_entries=50, max_concurrent=3)
    running = peak = 0

    def loader(key: int):
        async def load() -> int:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            running -= 1
            return key

        return load

    await asyncio.gather(*(cache.get(key, loader(key)) for key in range(20)))

    assert peak == 3


@pytest.mark.asyncio
async def test_a_cached_value_is_loaded_once_per_window_and_again_after_it() -> None:
    clock = _Clock()
    value: CachedValue[str] = CachedValue(ttl_seconds=300, clock=clock)
    load = _Loader("old", "new")

    assert [await value.get(load), await value.get(load)] == ["old", "old"]
    clock.now = 301
    assert await value.get(load) == "new"
    assert load.calls == 2
