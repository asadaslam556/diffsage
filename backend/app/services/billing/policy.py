"""Billing decisions as plain functions.

Everything here takes numbers in and gives a decision out. No database,
no HTTP, so the rules are easy to test and easy to read in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.errors import PermissionDenied, QuotaExceeded, ValidationFailed
from app.services.billing.plans import PlanDef


@dataclass(frozen=True)
class UsageSnapshot:
    requests_today: int
    tokens_this_month: int


def pick_provider(plan: PlanDef, requested: str | None, *, default: str, fallback: str) -> str:
    """Which provider this request should target.

    Asking for a provider your plan doesn't include is an error, not a
    silent downgrade. Otherwise the global default wins if the plan allows
    it, then the fallback.
    """
    if requested:
        if not plan.allows_provider(requested):
            raise PermissionDenied(
                f"The {plan.name} plan can't use {requested}. Upgrade to switch providers.",
                code="provider_not_in_plan",
            )
        return requested
    for candidate in (default, fallback, *plan.allowed_providers):
        if candidate != "*" and plan.allows_provider(candidate):
            return candidate
    raise PermissionDenied(f"The {plan.name} plan doesn't include any provider.", code="provider_not_in_plan")


def check_quota(plan: PlanDef, usage: UsageSnapshot, *, input_chars: int, now: datetime | None = None) -> None:
    """Raise if this request shouldn't run. Returns None if it's fine."""
    now = now or datetime.now(timezone.utc)
    if input_chars > plan.max_input_chars:
        raise ValidationFailed(
            f"That's {input_chars:,} characters; the {plan.name} plan takes up to {plan.max_input_chars:,} per request.",
            code="input_too_large",
        )
    if plan.daily_request_limit is not None and usage.requests_today >= plan.daily_request_limit:
        reset = next_day(now)
        raise QuotaExceeded(
            f"You've used all {plan.daily_request_limit} reviews for today on the {plan.name} plan. "
            f"It resets at {reset:%H:%M} UTC.",
            code="daily_limit_reached",
            headers={"Retry-After": str(int((reset - now).total_seconds()))},
        )
    if plan.monthly_token_limit is not None and usage.tokens_this_month >= plan.monthly_token_limit:
        raise QuotaExceeded(
            f"You've used this month's {plan.monthly_token_limit:,} tokens on the {plan.name} plan.",
            code="monthly_tokens_reached",
        )


def day_start(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def next_day(now: datetime) -> datetime:
    return day_start(now) + timedelta(days=1)


def month_start(now: datetime) -> datetime:
    return day_start(now).replace(day=1)


def estimate_tokens(text: str) -> int:
    # ~4 chars per token is close enough for billing when a provider
    # doesn't report usage (some local models don't)
    return max(1, len(text) // 4) if text else 0
