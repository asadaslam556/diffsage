"""The health endpoint has to reflect reality, so these break things on purpose."""

from __future__ import annotations

import asyncio
import dataclasses

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def test_liveness_is_public_and_cheap(client):
    response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_everything_up(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == {"database", "cache", "vector_db"}
    assert all(c["status"] == "ok" for c in body["components"].values())
    assert body["providers"]["ollama"]["status"] == "ok"
    # no key for deepseek in tests: reported, but not counted as an outage
    assert body["providers"]["deepseek"]["status"] == "not_configured"


async def test_vector_db_down_is_degraded_not_down(client, container):
    container.vector_store.healthy = False
    body = (await client.get("/api/health")).json()
    assert body["status"] == "degraded"
    assert body["components"]["vector_db"]["status"] == "down"
    assert "unhealthy" in body["components"]["vector_db"]["detail"]


async def test_one_paid_provider_down_is_degraded(client, container):
    container.providers["anthropic"]._health = "down"
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["providers"]["anthropic"]["status"] == "down"


async def test_database_down_returns_503(client, container, tmp_path):
    await container.engine.dispose()
    container.engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'nope.db'}", poolclass=NullPool,
    )
    response = await client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "down"
    assert body["components"]["database"]["status"] == "down"
    assert body["components"]["database"]["detail"]


async def test_no_usable_provider_returns_503(client, container):
    for provider in container.providers.values():
        provider._health = "down"
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "down"


async def test_hanging_provider_times_out_instead_of_hanging_health(client, container):
    from app.agent.providers.base import ProviderHealth

    async def never_answers():
        await asyncio.sleep(30)
        return ProviderHealth("ok")

    container.settings = dataclasses.replace(container.settings, health_check_timeout=0.2)
    container.providers["openai"].health_check = never_answers
    body = (await client.get("/api/health")).json()
    assert body["providers"]["openai"]["status"] == "down"
    assert "timed out" in body["providers"]["openai"]["detail"]
