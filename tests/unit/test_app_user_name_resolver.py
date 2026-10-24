from __future__ import annotations

import asyncio

import pytest

from openproject_ce_mcp.app.errors import NotFoundError, TransportError
from openproject_ce_mcp.app.resolvers.user_name_resolver import UserNameResolver


class _Api:
    def __init__(self, names: dict[int, object]) -> None:
        self._names = names
        self.calls: list[int] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def get_user_name(self, user_id: int):
        self.calls.append(user_id)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        outcome = self._names[user_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_each_distinct_user_is_asked_for_once() -> None:
    api = _Api({1: "Ada", 2: "Bob"})
    resolver = UserNameResolver(api=api)  # type: ignore[arg-type]

    names = await resolver.names([1, 2, 1, 2, 1])

    assert names == {1: "Ada", 2: "Bob"}
    assert sorted(api.calls) == [1, 2]


@pytest.mark.asyncio
async def test_a_name_is_remembered_for_a_while_and_then_asked_for_again() -> None:
    clock = _Clock()
    api = _Api({1: "Ada"})
    resolver = UserNameResolver(api=api, clock=clock)  # type: ignore[arg-type]

    await resolver.names([1])
    await resolver.names([1])
    clock.now = 301
    await resolver.names([1])

    assert api.calls == [1, 1]


@pytest.mark.asyncio
async def test_a_user_the_token_cannot_see_has_no_name_and_is_remembered_so() -> None:
    api = _Api({1: NotFoundError("gone")})
    resolver = UserNameResolver(api=api)  # type: ignore[arg-type]

    first = await resolver.names([1])
    second = await resolver.names([1])

    assert first == second == {1: None}
    assert api.calls == [1]


@pytest.mark.asyncio
async def test_any_other_failure_fails_the_call_and_is_not_remembered() -> None:
    api = _Api({1: TransportError("timeout")})
    resolver = UserNameResolver(api=api)  # type: ignore[arg-type]

    with pytest.raises(TransportError):
        await resolver.names([1])

    api._names[1] = "Ada"
    assert await resolver.names([1]) == {1: "Ada"}


@pytest.mark.asyncio
async def test_at_most_ten_users_are_asked_for_at_a_time() -> None:
    api = _Api({i: f"User {i}" for i in range(1, 31)})
    resolver = UserNameResolver(api=api)  # type: ignore[arg-type]

    await resolver.names(range(1, 31))

    assert 1 < api.max_in_flight <= 10
