"""Cache wrapper.

Redis in real life, a dict in tests. A cache miss is never an error: if
Redis is down, reads return None and writes are skipped, so the app just
gets slower instead of breaking.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

log = logging.getLogger(__name__)


class Cache(Protocol):
    async def get_json(self, key: str) -> Any | None: ...
    async def set_json(self, key: str, value: Any, ttl: int) -> None: ...
    async def delete(self, *keys: str) -> None: ...
    async def ping(self) -> bool: ...


class RedisCache:
    def __init__(self, redis: Any):
        self.redis = redis
        self._warned_at = 0.0

    def _warn(self, action: str, exc: Exception) -> None:
        # one warning a minute is plenty when Redis is down
        if time.monotonic() - self._warned_at > 60:
            log.warning("cache %s failed, carrying on without it: %s", action, exc)
            self._warned_at = time.monotonic()

    async def get_json(self, key: str) -> Any | None:
        try:
            raw = await self.redis.get(key)
        except Exception as exc:  # noqa: BLE001
            self._warn("get", exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        try:
            await self.redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception as exc:  # noqa: BLE001
            self._warn("set", exc)

    async def delete(self, *keys: str) -> None:
        if not keys:
            return
        try:
            await self.redis.delete(*keys)
        except Exception as exc:  # noqa: BLE001
            self._warn("delete", exc)

    async def ping(self) -> bool:
        return bool(await self.redis.ping())


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}

    async def get_json(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None or item[0] < time.monotonic():
            self._data.pop(key, None)
            return None
        return json.loads(item[1])

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        self._data[key] = (time.monotonic() + ttl, json.dumps(value, default=str))

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._data.pop(key, None)

    async def ping(self) -> bool:
        return True
