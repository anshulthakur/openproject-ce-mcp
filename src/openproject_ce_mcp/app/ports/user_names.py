"""The names of users that a server answer links by id only."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Protocol


class UserNames(Protocol):
    """Narrow seam onto `UserNameResolver.names`: the name of each user, or None for a user the
    token cannot see."""

    def __call__(self, user_ids: Iterable[int]) -> Awaitable[dict[int, str | None]]: ...
