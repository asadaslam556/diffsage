import asyncio

from app.core.config import RateLimitRule
from app.gateway.rate_limit import InMemoryRateLimiter
from app.gateway.routes import agent_may_call, match_route


class Clock:
    def __init__(self, now: float = 1_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks():
    async def go():
        limiter = InMemoryRateLimiter(clock=Clock())
        rule = RateLimitRule(limit=3, window_seconds=60)
        results = [await limiter.hit("u:1", rule) for _ in range(4)]
        assert [r.allowed for r in results] == [True, True, True, False]
        assert results[2].remaining == 0
        assert results[3].headers()["X-RateLimit-Remaining"] == "0"

    asyncio.run(go())


def test_window_rolls_over():
    async def go():
        clock = Clock(0.0)
        limiter = InMemoryRateLimiter(clock=clock)
        rule = RateLimitRule(limit=1, window_seconds=10)
        assert (await limiter.hit("k", rule)).allowed
        assert not (await limiter.hit("k", rule)).allowed
        clock.now = 10.5
        assert (await limiter.hit("k", rule)).allowed

    asyncio.run(go())


def test_keys_are_independent():
    async def go():
        limiter = InMemoryRateLimiter(clock=Clock())
        rule = RateLimitRule(limit=1, window_seconds=60)
        assert (await limiter.hit("u:a", rule)).allowed
        assert (await limiter.hit("u:b", rule)).allowed

    asyncio.run(go())


def test_reset_after_counts_down_to_window_end():
    async def go():
        limiter = InMemoryRateLimiter(clock=Clock(125.0))
        result = await limiter.hit("k", RateLimitRule(limit=5, window_seconds=60))
        assert result.reset_after == 55

    asyncio.run(go())


def test_route_table_longest_prefix_and_unknowns():
    assert match_route("/api/auth/login").rate_bucket == "auth"
    assert match_route("/api/auth/login").public
    assert match_route("/api/agent/chat").service == "agent"
    assert not match_route("/api/app/sessions").public
    assert match_route("/api/health").public
    assert match_route("/api/nope") is None
    assert match_route("/api/applesauce") is None  # prefix has to end on a path segment


def test_agent_tokens_are_read_only_and_narrow():
    assert agent_may_call("GET", "/api/app/documents/search")
    assert agent_may_call("GET", "/api/app/reviews/recent")
    assert not agent_may_call("POST", "/api/app/documents/search")
    assert not agent_may_call("POST", "/api/agent/chat")  # no recursive chats
    assert not agent_may_call("POST", "/api/billing/plan")
    assert not agent_may_call("GET", "/api/app/documents/search/../../billing")


def test_client_ip_ignores_addresses_the_client_wrote_itself():
    from starlette.datastructures import Headers

    from app.gateway.middleware import _client_ip

    scope = {"client": ("10.0.0.5", 1234)}
    spoofed = Headers({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert _client_ip(scope, spoofed, trust_proxy=True) == "203.0.113.9"
    assert _client_ip(scope, spoofed, trust_proxy=False) == "10.0.0.5"
