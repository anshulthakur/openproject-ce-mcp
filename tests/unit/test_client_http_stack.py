from __future__ import annotations

import ssl
from dataclasses import replace

import pytest
from _client_test_helpers import make_settings
from _loopback_http import connect_proxy, serve, socks5_proxy

from openproject_ce_mcp.app.errors import TransportError
from openproject_ce_mcp.client import OpenProjectClient
from openproject_ce_mcp.config import Settings


def _settings(base_url: str, **overrides: object) -> Settings:
    return replace(make_settings(), base_url=base_url, retry_base_delay=0.0, retry_max_delay=0.0, **overrides)


async def _get_current_user_name(settings: Settings) -> str:
    client = OpenProjectClient(settings)
    try:
        user = await client.current_user.get_current_user()
    finally:
        await client.aclose()
    return user.name


@pytest.mark.parametrize("max_retries", [0, 3])
async def test_verify_ssl_false_accepts_an_untrusted_certificate(
    without_proxies: None, server_ssl_context: ssl.SSLContext, max_retries: int
) -> None:
    async with serve([200], server_ssl_context) as server:
        settings = _settings(f"https://127.0.0.1:{server.port}", verify_ssl=False, max_retries=max_retries)

        assert await _get_current_user_name(settings) == "Test User"


@pytest.mark.parametrize("max_retries", [0, 3])
async def test_verify_ssl_true_rejects_an_untrusted_certificate(
    without_proxies: None, server_ssl_context: ssl.SSLContext, max_retries: int
) -> None:
    async with serve([200], server_ssl_context) as server:
        settings = _settings(f"https://127.0.0.1:{server.port}", verify_ssl=True, max_retries=max_retries)

        with pytest.raises(TransportError) as raised:
            await _get_current_user_name(settings)

        assert "CERTIFICATE_VERIFY_FAILED" in str(raised.value.__cause__)


@pytest.mark.parametrize("max_retries", [0, 3])
async def test_requests_go_through_the_proxy_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, without_proxies: None, max_retries: int
) -> None:
    async with serve([200]) as proxy:
        monkeypatch.delenv("NO_PROXY")
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy.port}")
        settings = _settings("http://op.invalid", max_retries=max_retries)

        assert await _get_current_user_name(settings) == "Test User"
        assert proxy.request_targets == ["http://op.invalid/api/v3/users/me"]


async def test_retries_apply_to_requests_through_the_proxy(
    monkeypatch: pytest.MonkeyPatch, without_proxies: None
) -> None:
    async with serve([503, 200]) as proxy:
        monkeypatch.delenv("NO_PROXY")
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy.port}")
        settings = _settings("http://op.invalid", max_retries=1)

        assert await _get_current_user_name(settings) == "Test User"
        assert len(proxy.request_targets) == 2


async def test_retries_apply_to_direct_requests(without_proxies: None) -> None:
    async with serve([503, 200]) as server:
        settings = _settings(f"http://127.0.0.1:{server.port}", max_retries=1)

        assert await _get_current_user_name(settings) == "Test User"
        assert server.request_targets == ["/api/v3/users/me", "/api/v3/users/me"]


@pytest.mark.parametrize("max_retries", [0, 3])
async def test_requests_go_through_a_socks_proxy_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, without_proxies: None, max_retries: int
) -> None:
    async with serve([200]) as server, socks5_proxy(server.port) as proxy:
        monkeypatch.delenv("NO_PROXY")
        monkeypatch.setenv("ALL_PROXY", f"socks5://127.0.0.1:{proxy.port}")
        settings = _settings("http://op.invalid", max_retries=max_retries)

        assert await _get_current_user_name(settings) == "Test User"
        assert proxy.destinations == ["op.invalid:80"]
        assert server.request_targets == ["/api/v3/users/me"]


async def test_no_proxy_hosts_bypass_the_proxy_and_keep_retries(
    monkeypatch: pytest.MonkeyPatch, without_proxies: None
) -> None:
    async with serve([200]) as proxy, serve([503, 200]) as server:
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy.port}")
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        settings = _settings(f"http://127.0.0.1:{server.port}", max_retries=1)

        assert await _get_current_user_name(settings) == "Test User"
        assert proxy.request_targets == []
        assert server.request_targets == ["/api/v3/users/me", "/api/v3/users/me"]


async def test_https_requests_tunnel_through_the_proxy_with_verify_ssl_and_retries(
    monkeypatch: pytest.MonkeyPatch, without_proxies: None, server_ssl_context: ssl.SSLContext
) -> None:
    async with serve([503, 200], server_ssl_context) as server, connect_proxy(server.port) as proxy:
        monkeypatch.delenv("NO_PROXY")
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{proxy.port}")
        settings = _settings("https://op.invalid", verify_ssl=False, max_retries=1)

        assert await _get_current_user_name(settings) == "Test User"
        assert proxy.destinations == ["op.invalid:443", "op.invalid:443"]
        assert server.request_targets == ["/api/v3/users/me", "/api/v3/users/me"]
