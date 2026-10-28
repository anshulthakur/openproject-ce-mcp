"""Query star Domain API port -- narrow, no universal gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class QueryStarRecord:
    """A saved query as far as starring needs it. `owner_id` is the id of the user the query belongs to.
    `can_star` and `can_unstar` are whether OpenProject offers the matching link to this caller, which is how it
    says the caller may use that route."""

    query_id: int
    starred: bool
    public: bool
    project_link: dict[str, Any] | None
    owner_id: int | None
    can_star: bool
    can_unstar: bool


class QueryStarApi(Protocol):
    async def get(self, query_id: int) -> QueryStarRecord: ...
    async def set_starred(self, query_id: int, *, starred: bool) -> None: ...
