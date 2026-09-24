"""Shared fixtures for the API tests.

The whole app runs in-process: SQLite instead of Postgres, dicts instead of
Redis and Qdrant, and scripted fake providers instead of real models. The
agent's gateway callbacks are pointed back at the same ASGI app, so the
"agent may call again" path gets exercised for real.

The pure unit tests (rate limiter, wire parsing, billing policy...) don't
touch any of this.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

# keep the test run away from any .env on the dev machine
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-definitely-long-enough-0123456789")

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.agent.providers.router import ProviderRouter  # noqa: E402
from app.cache.store import MemoryCache  # noqa: E402
from app.container import Container  # noqa: E402
from app.core.config import DEFAULT_SETTINGS_FILE, Settings, load_settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import create_sessionmaker, sync_plans  # noqa: E402
from app.gateway.rate_limit import InMemoryRateLimiter  # noqa: E402
from app.main import create_app  # noqa: E402
from app.vectorstore.embeddings import HashingEmbedder  # noqa: E402
from app.vectorstore.store import MemoryVectorStore  # noqa: E402
from tests.fakes import FakeProvider  # noqa: E402

PASSWORD = "correct horse battery"


def make_settings(tmp_path: Path, **overrides: str) -> Settings:
    env = {
        "JWT_SECRET": os.environ["JWT_SECRET"],
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        "AUTH__PASSWORD_HASH_ITERATIONS": "1000",  # 600k is great in prod, painful in tests
        "EMBEDDINGS__BACKEND": "hashing",
        "EMBEDDINGS__DIM": "256",
        "BILLING__ALLOW_SELF_SERVE_PLAN_CHANGE": "true",
        "HEALTH__PROVIDER_CACHE_SECONDS": "0",
        "AGENT__FIRST_TOKEN_TIMEOUT_SECONDS": "2",
        **overrides,
    }
    return load_settings(DEFAULT_SETTINGS_FILE, env)


def default_providers() -> dict[str, FakeProvider]:
    return {
        "ollama": FakeProvider("ollama"),
        "anthropic": FakeProvider("anthropic"),
        "openai": FakeProvider("openai"),
        "deepseek": FakeProvider("deepseek", configured=False),
    }


async def make_container(settings: Settings, providers: dict[str, FakeProvider] | None = None) -> Container:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = create_sessionmaker(engine)
    await sync_plans(sessionmaker)
    providers = providers or default_providers()
    return Container(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        cache=MemoryCache(),
        rate_limiter=InMemoryRateLimiter(),
        vector_store=MemoryVectorStore(),
        embedder=HashingEmbedder(settings.embedding_dim),
        providers=providers,
        router=ProviderRouter(
            providers, default=settings.default_provider, fallback=settings.fallback_chain,
            first_token_timeout=settings.first_token_timeout,
        ),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    c = await make_container(settings)
    yield c
    await c.engine.dispose()


@pytest.fixture
async def client(container: Container) -> AsyncIterator["httpx.AsyncClient"]:
    app = create_app(container=container)
    transport = httpx.ASGITransport(app=app)
    # the agent's tools call back into this same app instead of over TCP
    container.gateway_transport = transport
    async with httpx.AsyncClient(transport=transport, base_url="http://app.test") as c:
        yield c


async def register(client: "httpx.AsyncClient", email: str = "dev@example.com") -> dict:
    response = await client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def auth(client: "httpx.AsyncClient") -> dict[str, str]:
    body = await register(client)
    return bearer(body["access_token"])


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    """Turn a full SSE body into [(event, data), ...]."""
    import json

    events = []
    for block in raw.split("\n\n"):
        name, data = "message", []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((name, json.loads("\n".join(data))))
    return events
