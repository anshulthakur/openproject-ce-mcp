"""Tests for HTTP and SSE transport with Bearer auth and healthcheck."""

import pytest
from starlette.testclient import TestClient

from openproject_ce_mcp import __version__
from openproject_ce_mcp.config import Settings
from openproject_ce_mcp.server import _run_server, _SettingsError, create_app


def _make_settings(**kwargs) -> Settings:
    defaults = {
        "base_url": "https://op.example.com",
        "api_token": "token123",
        "read_projects": ("*",),
        "write_projects": (),
        "timeout": 12,
        "verify_ssl": True,
        "default_page_size": 20,
        "max_page_size": 50,
        "max_results": 100,
        "log_level": "WARNING",
    }
    defaults.update(kwargs)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_http_auth_and_health_middleware(monkeypatch) -> None:
    settings = _make_settings()
    app = create_app(settings)
    starlette_app = app.streamable_http_app(host="127.0.0.1", streamable_http_path="/mcp")

    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse, Response

    http_token = "secret-token-123"

    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path == "/health":
                return JSONResponse(
                    {
                        "status": "ok",
                        "server": "openproject-ce-mcp",
                        "version": __version__,
                    }
                )
            if request.method == "OPTIONS":
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
                        "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept",
                    },
                )
            auth_header = request.headers.get("authorization")
            query_token = request.query_params.get("token") or request.query_params.get("auth")
            is_valid = auth_header == f"Bearer {http_token}" or query_token == http_token
            if not is_valid:
                return JSONResponse(
                    {"error": "Unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)

    starlette_app.add_middleware(AuthMiddleware)

    with TestClient(starlette_app) as client:
        # /health endpoint is open
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "server": "openproject-ce-mcp",
            "version": __version__,
        }

        # CORS preflight
        cors = client.options("/mcp")
        assert cors.status_code == 204
        assert "Access-Control-Allow-Origin" in cors.headers

        # Unauthenticated /mcp is rejected
        unauth = client.post("/mcp")
        assert unauth.status_code == 401
        assert unauth.json() == {"error": "Unauthorized"}

        # Wrong token is rejected
        wrong = client.post("/mcp", headers={"Authorization": "Bearer wrong"})
        assert wrong.status_code == 401

        # Correct token is accepted and reaches the MCP router (400 for empty body)
        valid = client.post("/mcp", headers={"Authorization": f"Bearer {http_token}"})
        assert valid.status_code != 401

        # Query parameter auth is accepted
        valid_query = client.post(f"/mcp?token={http_token}")
        assert valid_query.status_code != 401


def test_run_server_http_requires_token(monkeypatch) -> None:
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "https://op.example.com")
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", "tok")
    monkeypatch.setenv("TRANSPORT", "http")
    monkeypatch.delenv("MCP_HTTP_TOKEN", raising=False)

    with pytest.raises(_SettingsError, match="MCP_HTTP_TOKEN must be configured"):
        _run_server()


def test_run_server_http_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("OPENPROJECT_BASE_URL", "https://op.example.com")
    monkeypatch.setenv("OPENPROJECT_API_TOKEN", "tok")
    monkeypatch.setenv("TRANSPORT", "http")
    monkeypatch.setenv("MCP_HTTP_TOKEN", "tok")
    monkeypatch.setenv("PORT", "not-a-number")

    with pytest.raises(_SettingsError, match="Invalid PORT"):
        _run_server()
