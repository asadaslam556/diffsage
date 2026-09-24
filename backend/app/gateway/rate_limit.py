"""Fixed-window rate limiting.

Fixed windows are a bit bursty at the boundary (someone can do 2x the limit
across two adjacent windows) but they're one INCR per request and easy to
reason about. For an API like this that's the right trade.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import RateLimitRule

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after: int  # seconds until the window rolls over

    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_after),
        }


class RateLimiter(Protocol):
    async def hit(self, key: str, rule: RateLimitRule) -> RateLimitResult: ...


def _window(now: float, rule: RateLimitRule) -> tuple[int, int]:
    index = int(now // rule.window_seconds)
    reset_after = max(1, math.ceil((index + 1) * rule.window_seconds - now))
    return index, reset_after


class InMemoryRateLimiter:
    """Single-process only. Used in tests and as the dev fallback."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._counts: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        async with self._lock:
            index, reset_after = _window(self._clock(), rule)
            window, count = self._counts.get(key, (index, 0))
            if window != index:
                count = 0
            count += 1
            self._counts[key] = (index, count)
            if len(self._counts) > 50_000:  # crude cleanup so it can't grow forever
                self._counts = {k: v for k, v in self._counts.items() if v[0] == index}
        return RateLimitResult(count <= rule.limit, rule.limit, rule.limit - count, reset_after)


class RedisRateLimiter:
    def __init__(self, redis: Any, prefix: str = "rl", clock: Callable[[], float] = time.time):
        self.redis = redis
        self.prefix = prefix
        self._clock = clock

    async def hit(self, key: str, rule: RateLimitRule) -> RateLimitResult:
        index, reset_after = _window(self._clock(), rule)
        redis_key = f"{self.prefix}:{key}:{index}"
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, rule.window_seconds + 5)
            count, _ = await pipe.execute()
        count = int(count)
        return RateLimitResult(count <= rule.limit, rule.limit, rule.limit - count, reset_after)
