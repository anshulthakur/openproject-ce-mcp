"""Current-user lookup port.

The caller's own user, read through `CurrentUserApi` with no read gate and no masking: it is what
`"me"` stands for in a filter or a write, not a user lookup a caller asked for. `UserApi.get_user("me")`
is not a substitute, because it is gated and its result is truncated and masked.

Implemented by `app/resolvers/current_user_resolver.py`'s
`CurrentUserResolver`, which depends directly on `CurrentUserApi` -- not by
a bound method on a Service or on `client.py`, so no consumer of this seam
carries a hidden Service dependency.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol

from ...models import CurrentUser


class CurrentUserLookup(Protocol):
    def __call__(self) -> Awaitable[CurrentUser]: ...
