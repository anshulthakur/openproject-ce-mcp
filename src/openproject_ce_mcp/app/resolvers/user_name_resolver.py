"""The names of the users an activity links by id only.

OpenProject renders the user of an activity as a link without a title, so the name comes from one
`GET users/{id}` per distinct user, remembered for a while. It checks no read gate: it names the
author of something the caller may already read, and the read gate of the user tools belongs to
them. A user the token cannot see has no name.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from functools import partial

from ...context_gather import gather_in_current_context
from ..caches import LoadingCache
from ..errors import NotFoundError
from ..ports.principal_api import PrincipalApi

_LOOKUP_CONCURRENCY = 10
_MAX_ENTRIES = 1024


class UserNameResolver:
    def __init__(self, *, api: PrincipalApi, clock: Callable[[], float] = time.monotonic) -> None:
        self._api = api
        self._names: LoadingCache[int, str | None] = LoadingCache(
            max_entries=_MAX_ENTRIES, max_concurrent=_LOOKUP_CONCURRENCY, clock=clock
        )

    async def names(self, user_ids: Iterable[int]) -> dict[int, str | None]:
        """The name of each distinct user id; any failure but `NotFoundError` fails the call."""
        distinct = list(dict.fromkeys(user_ids))
        found = await gather_in_current_context(
            *(self._names.get(user_id, partial(self._read, user_id)) for user_id in distinct)
        )
        return dict(zip(distinct, found, strict=True))

    async def _read(self, user_id: int) -> str | None:
        try:
            return await self._api.get_user_name(user_id)
        except NotFoundError:
            return None
