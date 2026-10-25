"""Current-user lookup resolver -- the `CurrentUserLookup` seam's own implementation.

Depends on `CurrentUserApi` only. It is an internal lookup for `assignee="me"`, `user="me"` and the
`assigned to me` filters, so it checks no read gate and masks no field: the tool `get_current_user`
(`CurrentUserService`) owns both, and a write of another domain must keep working when reads of
users are off. `cache` is the `CachedValue` that `client.py` also gives `CurrentUserService`.
"""

from __future__ import annotations

from ...models import CurrentUser
from ..caches import CachedValue
from ..ports.current_user_api import CurrentUserApi, CurrentUserRecord


class CurrentUserResolver:
    def __init__(self, *, api: CurrentUserApi, cache: CachedValue[CurrentUserRecord]) -> None:
        self._api = api
        self._cache = cache

    async def __call__(self) -> CurrentUser:
        return (await self._cache.get(self._api.get_current_user)).summary
