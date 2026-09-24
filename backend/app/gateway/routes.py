"""The gateway's route table.

Every /api path has to match one of these, and the entry decides three
things: which service owns it, whether it needs a token, and which rate
limit bucket it counts against. Anything under /api that isn't in here
gets a 404 from the gateway before it reaches a router.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayRoute:
    prefix: str
    service: str
    public: bool = False
    rate_bucket: str = "default"


ROUTES: tuple[GatewayRoute, ...] = (
    GatewayRoute("/api/health", "health", public=True),
    GatewayRoute("/api/auth", "business", public=True, rate_bucket="auth"),
    GatewayRoute("/api/app", "business"),
    GatewayRoute("/api/agent", "agent", rate_bucket="agent"),
    GatewayRoute("/api/billing", "billing"),
)

# longest prefix first so /api/app/x never matches a shorter /api rule
_SORTED = sorted(ROUTES, key=lambda r: len(r.prefix), reverse=True)


def match_route(path: str) -> GatewayRoute | None:
    for route in _SORTED:
        if path == route.prefix or path.startswith(route.prefix + "/"):
            return route
    return None


# The agent's short-lived tokens only get read access to the handful of
# endpoints its tools actually use. If a prompt injection talks the model
# into something creative, the gateway still says no.
AGENT_ALLOWED: tuple[tuple[str, str], ...] = (
    ("GET", "/api/app/documents/search"),
    ("GET", "/api/app/reviews/recent"),
)


def agent_may_call(method: str, path: str) -> bool:
    return any(method == m and path == p for m, p in AGENT_ALLOWED)
