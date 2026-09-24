"""Real health checks.

Each component gets probed for real (SELECT 1, PING, Qdrant's collections
endpoint, each provider's cheapest endpoint) with a timeout, all at once.
Provider results are cached for a few seconds so a monitoring system polling
this every 5s doesn't turn into a steady stream of calls to paid APIs.

Overall status:
  down      database is down, or no model provider works at all
  degraded  something non-essential is off (Redis, Qdrant, one provider)
  ok        everything answered
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from typing import Any

from app.container import Container
from app.db.session import ping as db_ping

log = logging.getLogger(__name__)


async def _timed(coro: Awaitable[Any], timeout: float) -> tuple[bool, str, int]:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return False, f"timed out after {timeout:g}s", int((time.perf_counter() - started) * 1000)
    except Exception as exc:  # noqa: BLE001
        return False, f"{exc.__class__.__name__}: {str(exc)[:200]}", int((time.perf_counter() - started) * 1000)
    latency = int((time.perf_counter() - started) * 1000)
    if isinstance(result, tuple):  # vector store returns (ok, detail)
        return bool(result[0]), result[1], latency
    if result is False:
        return False, "check returned false", latency
    return True, "", latency


async def _check_providers(container: Container, timeout: float) -> dict[str, dict[str, Any]]:
    cached = container.health_cache.get("providers")
    if cached and cached["expires"] > time.monotonic():
        return cached["data"]

    async def one(name: str) -> tuple[str, dict[str, Any]]:
        provider = container.providers[name]
        if not provider.is_configured():
            return name, {"status": "not_configured", "detail": "no API key set" if provider.requires_api_key else "disabled", "model": provider.model}
        try:
            health = await asyncio.wait_for(provider.health_check(), timeout=timeout)
        except asyncio.TimeoutError:
            return name, {"status": "down", "detail": f"timed out after {timeout:g}s", "model": provider.model}
        except Exception as exc:  # noqa: BLE001
            log.warning("health check for %s raised", name, exc_info=True)
            return name, {"status": "down", "detail": f"{exc.__class__.__name__}: {exc}", "model": provider.model}
        return name, {"status": health.status, "detail": health.detail, "latency_ms": health.latency_ms, "model": provider.model}

    results = dict(await asyncio.gather(*(one(n) for n in container.providers)))
    container.health_cache["providers"] = {
        "data": results, "expires": time.monotonic() + container.settings.health_provider_cache_seconds,
    }
    return results


async def run_health_checks(container: Container) -> dict[str, Any]:
    timeout = container.settings.health_check_timeout
    db, cache, vectors, providers = await asyncio.gather(
        _timed(db_ping(container.engine), timeout),
        _timed(container.cache.ping(), timeout),
        _timed(container.vector_store.health(), timeout),
        _check_providers(container, timeout),
    )

    def component(result: tuple[bool, str, int], *, critical: bool) -> dict[str, Any]:
        ok, detail, latency = result
        return {"status": "ok" if ok else "down", "detail": detail, "latency_ms": latency, "critical": critical}

    components = {
        "database": component(db, critical=True),
        "cache": component(cache, critical=False),
        "vector_db": component(vectors, critical=False),
    }
    usable = [n for n, p in providers.items() if p["status"] in ("ok", "degraded")]
    fallback = container.settings.fallback_provider

    if components["database"]["status"] != "ok" or not usable:
        overall = "down"
    elif any(c["status"] != "ok" for c in components.values()) or providers.get(fallback, {}).get("status") != "ok" \
            or any(p["status"] in ("down", "degraded") for p in providers.values()):
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "components": components,
        "providers": providers,
        "default_provider": container.settings.default_provider,
        "fallback_provider": fallback,
    }
