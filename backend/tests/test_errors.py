"""What callers see when something underneath breaks."""

import socket

import httpx

from app.main import create_app


async def _client_with(container, path, exc):
    app = create_app(container=container)

    async def boom():
        raise exc

    # /api/health/* is a public gateway route, so no token needed for the test endpoint
    app.add_api_route(path, boom)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://app.test")


async def test_unresolvable_database_host_is_a_503_not_a_500(container):
    # what asyncpg raises when the postgres container is gone
    async with await _client_with(container, "/api/health/db-gone", socket.gaierror(-2, "Name or service not known")) as c:
        r = await c.get("/api/health/db-gone")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "service_unavailable"


async def test_unexpected_errors_keep_their_request_id(container):
    async with await _client_with(container, "/api/health/bug", RuntimeError("oops")) as c:
        r = await c.get("/api/health/bug", headers={"x-request-id": "trace-me-123"})
    assert r.status_code == 500
    assert r.json()["error"]["request_id"] == "trace-me-123"
    assert r.headers["x-request-id"] == "trace-me-123"
    assert "oops" not in r.text  # internals stay in the log, not the response
