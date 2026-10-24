"""Process-lifetime cache holders for read-only, process-global API responses.

`SingletonCache` deliberately holds no gating/masking logic of its own --
`client.py` constructs one instance per cached value and shares the same
reference across every consumer that needs it (same shape as
`_project_id_to_identifier`), so a Service and a Resolver with different
read-gate behavior (see `StatusPriorityTypeResolver`'s docstring) can safely
share one cache without either inheriting the other's gate check.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


@dataclass
class SingletonCache(Generic[T]):
    value: T | None = None


class TtlCache(Generic[K, V]):
    """A bounded memory of lookups that expires, for values the server can change but rarely does.
    Reads and writes are not locked: the event loop is the only caller, and a lost write costs one
    repeated request."""

    def __init__(self, *, ttl_seconds: float, max_entries: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> tuple[V] | None:
        """The remembered value in a one-tuple (a remembered None is not a miss), or None when the
        key is unknown or its entry has expired."""
        entry = self._entries.get(key)
        if entry is None or self._clock() - entry[0] > self._ttl_seconds:
            return None
        self._entries.move_to_end(key)
        return (entry[1],)

    def put(self, key: K, value: V) -> None:
        self._entries[key] = (self._clock(), value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
