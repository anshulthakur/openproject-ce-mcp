"""HTTP-backed QueryStarApi adapter."""

from __future__ import annotations

from ..ports.query_star_api import QueryStarRecord
from ..transport.protocol import Transport
from ._text import id_from_href as _id_from_href


class HttpxQueryStarApi:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def get(self, query_id: int) -> QueryStarRecord:
        # pageSize 0 keeps the server from running the query and embedding its work packages.
        payload = await self._transport.get_json(f"queries/{query_id}", params={"pageSize": "0"})
        links = payload.get("_links", {})
        owner_link = links.get("user")
        return QueryStarRecord(
            query_id=int(payload["id"]),
            starred=bool(payload.get("starred")),
            public=bool(payload.get("public")),
            project_link=links.get("project"),
            owner_id=_id_from_href(owner_link.get("href")) if isinstance(owner_link, dict) else None,
            can_star="star" in links,
            can_unstar="unstar" in links,
        )

    async def set_starred(self, query_id: int, *, starred: bool) -> None:
        # An empty dict, not None: a bodyless PATCH sends no Content-Type header and OpenProject answers 406.
        await self._transport.request_raw(
            "PATCH", f"queries/{query_id}/{'star' if starred else 'unstar'}", json_body={}
        )
