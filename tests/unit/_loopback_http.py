"""Loopback OpenProject, HTTP CONNECT and SOCKS5 servers for HTTP-stack tests."""

from __future__ import annotations

import asyncio
import base64
import json
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
USER = {"_type": "User", "id": 1, "name": "Test User", "login": "test"}


@dataclass
class Server:
    port: int
    statuses: list[int]
    request_targets: list[str] = field(default_factory=list)


@asynccontextmanager
async def serve(
    statuses: list[int], ssl_context: ssl.SSLContext | None = None, *, echo_credentials: bool = False
) -> AsyncIterator[Server]:
    """``echo_credentials`` repeats the request head and the decoded Basic credentials, as a
    hostile server could: in an error's message, or in the user's name on a 200."""
    server_state = Server(port=0, statuses=statuses)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionResetError, ssl.SSLError):
            writer.close()
            return
        server_state.request_targets.append(head.split(b" ", 2)[1].decode())
        status = server_state.statuses.pop(0) if len(server_state.statuses) > 1 else server_state.statuses[0]
        body = json.dumps(_echo(head, status) if echo_credentials else USER).encode()
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=ssl_context)
    server_state.port = server.sockets[0].getsockname()[1]
    async with server:
        yield server_state


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()


async def relay(
    client: tuple[asyncio.StreamReader, asyncio.StreamWriter],
    upstream: tuple[asyncio.StreamReader, asyncio.StreamWriter],
) -> None:
    # Closing only the side that ended leaves the other one open, and a TLS
    # server then waits out its 30-second shutdown timeout for the peer.
    pipes = [
        asyncio.create_task(pipe(client[0], upstream[1])),
        asyncio.create_task(pipe(upstream[0], client[1])),
    ]
    await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
    for task in pipes:
        task.cancel()
    client[1].close()
    upstream[1].close()


@dataclass
class Proxy:
    port: int
    destinations: list[str] = field(default_factory=list)


@asynccontextmanager
async def socks5_proxy(forward_port: int) -> AsyncIterator[Proxy]:
    """Relays every destination to `forward_port`, so tests can name hosts that do not resolve."""
    proxy_state = Proxy(port=0)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        _, method_count = await reader.readexactly(2)
        await reader.readexactly(method_count)
        writer.write(b"\x05\x00")
        _, _, _, address_type = await reader.readexactly(4)
        assert address_type == 3, "the client sends the host name, not a resolved address"
        host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
        port = int.from_bytes(await reader.readexactly(2), "big")
        proxy_state.destinations.append(f"{host}:{port}")
        upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", forward_port)
        writer.write(b"\x05\x00\x00\x01" + bytes(6))
        await writer.drain()
        await relay((reader, writer), (upstream_reader, upstream_writer))

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    proxy_state.port = server.sockets[0].getsockname()[1]
    async with server:
        yield proxy_state


@asynccontextmanager
async def connect_proxy(forward_port: int) -> AsyncIterator[Proxy]:
    """Relays every destination to `forward_port`, so tests can name hosts that do not resolve."""
    proxy_state = Proxy(port=0)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        method, destination, _ = head.split(b" ", 2)
        assert method == b"CONNECT"
        proxy_state.destinations.append(destination.decode())
        upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", forward_port)
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        await relay((reader, writer), (upstream_reader, upstream_writer))

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    proxy_state.port = server.sockets[0].getsockname()[1]
    async with server:
        yield proxy_state


def _echo(head: bytes, status: int) -> dict[str, object]:
    text = head.decode(errors="replace")
    decoded = ""
    for line in text.split("\r\n"):
        if line.lower().startswith("authorization: basic "):
            decoded = base64.b64decode(line.split(" ", 2)[2]).decode(errors="replace")
    if status == 200:
        return {**USER, "name": f"{text} {decoded}"}
    return {
        "_type": "Error",
        "errorIdentifier": "urn:openproject-org:api:v3:errors:Unauthenticated",
        "message": f"{text} {decoded}",
    }
