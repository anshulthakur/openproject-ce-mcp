"""Fixtures for the loopback HTTP-stack tests."""

from __future__ import annotations

import ssl

import pytest
import trustme
from _loopback_http import PROXY_VARS


@pytest.fixture
def without_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    # A set NO_PROXY keeps urllib from falling back to the OS proxy settings.
    monkeypatch.setenv("NO_PROXY", "*")


@pytest.fixture
def ca() -> trustme.CA:
    return trustme.CA()


@pytest.fixture
def server_ssl_context(ca: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("127.0.0.1").configure_cert(context)
    return context
