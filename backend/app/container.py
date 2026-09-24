"""Builds and tears down everything the app talks to.

One object, created once at startup and hung on app.state. Tests build
their own with SQLite, in-memory cache and fake providers, which is the
whole reason this exists instead of module-level globals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent.providers.base import LLMProvider
from app.agent.providers.registry import build_providers
from app.agent.providers.router import ProviderRouter
from app.cache.store import Cache, RedisCache
from app.core.config import Settings
from app.db.session import create_engine, create_sessionmaker, sync_plans
from app.gateway.rate_limit import RateLimiter, RedisRateLimiter
from app.vectorstore.embeddings import Embedder, HashingEmbedder, ProviderEmbedder
from app.vectorstore.store import QdrantStore, VectorStore

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    cache: Cache
    rate_limiter: RateLimiter
    vector_store: VectorStore
    embedder: Embedder
    providers: dict[str, LLMProvider]
    router: ProviderRouter
    redis: Any | None = None
    # lets tests route the agent's gateway calls in-process instead of over TCP
    gateway_transport: Any | None = None
    health_cache: dict[str, Any] = field(default_factory=dict)


def make_embedder(settings: Settings, providers: dict[str, LLMProvider]) -> Embedder:
    if settings.embedding_backend == "hashing":
        return HashingEmbedder(settings.embedding_dim)
    provider = providers.get(settings.embedding_backend)
    if provider is None:
        log.error("embeddings.backend '%s' isn't a provider, falling back to hashing", settings.embedding_backend)
        return HashingEmbedder(settings.embedding_dim)
    return ProviderEmbedder(provider, settings.embedding_model, settings.embedding_dim)


async def build_container(settings: Settings) -> Container:
    import redis.asyncio as redis_async

    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)
    try:
        await sync_plans(sessionmaker)
    except Exception:  # noqa: BLE001
        # don't crash-loop the container if postgres is a few seconds late;
        # /api/health will show the database as down until it's back
        log.exception("couldn't sync plans at startup (database down or not migrated?)")

    redis = redis_async.from_url(
        settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2,
    )
    providers = build_providers(settings.providers)
    router = ProviderRouter(
        providers,
        default=settings.default_provider,
        fallback=settings.fallback_chain,
        first_token_timeout=settings.first_token_timeout,
    )
    return Container(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        cache=RedisCache(redis),
        rate_limiter=RedisRateLimiter(redis),
        vector_store=QdrantStore(settings.qdrant_url, settings.vector_collection, settings.embedding_dim, settings.qdrant_api_key),
        embedder=make_embedder(settings, providers),
        providers=providers,
        router=router,
        redis=redis,
    )


async def close_container(container: Container) -> None:
    for provider in container.providers.values():
        try:
            await provider.aclose()
        except Exception:  # noqa: BLE001
            log.warning("error closing provider %s", provider.name, exc_info=True)
    closer = getattr(container.vector_store, "aclose", None)
    if closer:
        await closer()
    if container.redis is not None:
        await container.redis.aclose()
    await container.engine.dispose()
