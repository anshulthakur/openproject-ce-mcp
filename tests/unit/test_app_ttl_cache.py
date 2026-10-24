from __future__ import annotations

from openproject_ce_mcp.app.caches import TtlCache


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
