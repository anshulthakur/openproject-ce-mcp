"""The names of the users an activity links by id only.

OpenProject renders the user of an activity as a link without a title, so the name comes from one
`GET users/{id}` per distinct user, remembered for a while. It checks no read gate: it names the
author of something the caller may already read, and the read gate of the user tools belongs to
them. A user the token cannot see has no name.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable

from ..caches import TtlCache
from ..errors import NotFoundError
from ..ports.principal_api import PrincipalApi

_LOOKUP_CONCURRENCY = 10
_FRESHNESS_SECONDS = 300.0
_MAX_ENTRIES = 1024


class UserNameResolver:
    def __init__(self, *, api: PrincipalApi, clock: Callable[[], float] = time.monotonic) -> None:
        self._api = api
        self._semaphore = asyncio.Semaphore(_LOOKUP_CONCURRENCY)
        self._known: TtlCache[int, str | None] = TtlCache(
            ttl_seconds=_FRESHNESS_SECONDS, max_entries=_MAX_ENTRIES, clock=clock
        )

    async def names(self, user_ids: Iterable[int]) -> dict[int, str | None]:
        """The name of each distinct user id; any failure but `NotFoundError` fails the call."""
        names: dict[int, str | None] = {}
        lookups: list[int] = []
        for user_id in dict.fromkeys(user_ids):
            remembered = self._known.get(user_id)
            if remembered is None:
                lookups.append(user_id)
            else:
                names[user_id] = remembered[0]

        async def look_up(user_id: int) -> None:
            async with self._semaphore:
                try:
                    name = await self._api.get_user_name(user_id)
                except NotFoundError:
                    name = None
            self._known.put(user_id, name)
            names[user_id] = name

        await asyncio.gather(*(look_up(user_id) for user_id in lookups))
        return names
