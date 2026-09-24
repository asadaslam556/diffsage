"""Plan definitions. Code is the source of truth; they get upserted into
the plans table on startup so the database always matches what's deployed."""

from __future__ import annotations

from dataclasses import dataclass

ALL_PROVIDERS = "*"


@dataclass(frozen=True)
class PlanDef:
    id: str
    name: str
    price_cents: int
    daily_request_limit: int | None      # None = unlimited
    monthly_token_limit: int | None
    allowed_providers: tuple[str, ...]   # ("*",) = any configured provider
    can_switch_provider: bool
    max_input_chars: int

    def allows_provider(self, name: str) -> bool:
        return ALL_PROVIDERS in self.allowed_providers or name in self.allowed_providers


PLANS: dict[str, PlanDef] = {
    "free": PlanDef(
        id="free", name="Free", price_cents=0,
        daily_request_limit=25, monthly_token_limit=300_000,
        allowed_providers=("ollama",), can_switch_provider=False,
        max_input_chars=12_000,
    ),
    "pro": PlanDef(
        id="pro", name="Pro", price_cents=1_900,
        daily_request_limit=500, monthly_token_limit=5_000_000,
        allowed_providers=(ALL_PROVIDERS,), can_switch_provider=True,
        max_input_chars=60_000,
    ),
    "team": PlanDef(
        id="team", name="Team", price_cents=4_900,
        daily_request_limit=None, monthly_token_limit=None,
        allowed_providers=(ALL_PROVIDERS,), can_switch_provider=True,
        max_input_chars=150_000,
    ),
}

DEFAULT_PLAN = "free"
