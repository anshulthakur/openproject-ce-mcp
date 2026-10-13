"""A Transport that shows every JSON response body to a learner first.

Scope policies are synchronous and read state that must already know every
project a response refers to; awaiting the learner here, before the body
reaches any adapter, is what makes that true for every caller at once.

The learner is told when each request was sent, since a body describes the
server as of that moment, however late it arrives.
"""

from __future__ import annotations

from typing import Any, Protocol

from .protocol import BinaryContent, Transport, TransportResponse


class ResponseLearner(Protocol):
    def request_sent(self) -> int: ...

    async def learn(self, payload: Any, *, sent: int) -> None: ...


class LearningTransport:
    def __init__(self, inner: Transport, *, learner: ResponseLearner) -> None:
        self._inner = inner
        self._learner = learner

    async def _learned(self, body: dict[str, Any], sent: int) -> dict[str, Any]:
        await self._learner.learn(body, sent=sent)
        return body

    async def get_json(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(await self._inner.get_json(path, params=params), sent)

    async def get_binary(self, path: str, *, max_bytes: int) -> BinaryContent:
        return await self._inner.get_binary(path, max_bytes=max_bytes)

    async def post_json(
        self, path: str, *, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(await self._inner.post_json(path, params=params, json_body=json_body), sent)

    async def post_raw_json(self, path: str, *, content: bytes, headers: dict[str, str]) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(await self._inner.post_raw_json(path, content=content, headers=headers), sent)

    async def post_multipart(
        self,
        path: str,
        *,
        metadata: dict[str, Any],
        file_name: str,
        file_bytes: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(
            await self._inner.post_multipart(
                path, metadata=metadata, file_name=file_name, file_bytes=file_bytes, content_type=content_type
            ),
            sent,
        )

    async def patch_json(
        self, path: str, *, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(await self._inner.patch_json(path, params=params, json_body=json_body), sent)

    async def delete(self, path: str, *, params: dict[str, str] | None = None) -> None:
        await self._inner.delete(path, params=params)

    async def delete_json(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        sent = self._learner.request_sent()
        return await self._learned(await self._inner.delete_json(path, params=params), sent)

    async def request_raw(
        self, method: str, path: str, *, params: dict[str, str] | None = None, json_body: dict[str, Any] | None = None
    ) -> TransportResponse:
        return await self._inner.request_raw(method, path, params=params, json_body=json_body)
