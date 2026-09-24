"""Usage tracking and quota lookups against the database, with a short
Redis cache in front so the quota check on every chat request is one GET
instead of two aggregate queries."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.store import Cache
from app.db.models import UsageRecord, User
from app.services.billing.plans import PLANS, PlanDef
from app.services.billing.policy import UsageSnapshot, day_start, month_start, next_day

log = logging.getLogger(__name__)

# statuses that count against the plan. A request that errored out
# before producing anything doesn't cost the user a review.
BILLABLE = ("ok", "fallback", "cancelled")
SNAPSHOT_TTL = 60


def plan_for(user: User) -> PlanDef:
    plan = PLANS.get(user.plan_id)
    if plan is None:
        # a plan removed from code but still on a user row; treat as free, loudly
        log.error("user %s has unknown plan %r, treating as free", user.id, user.plan_id)
        return PLANS["free"]
    return plan


class BillingService:
    def __init__(self, db: AsyncSession, cache: Cache):
        self.db = db
        self.cache = cache

    def _key(self, user_id: uuid.UUID, now: datetime) -> str:
        return f"usage:{user_id}:{now:%Y-%m-%d}"

    async def snapshot(self, user_id: uuid.UUID, now: datetime | None = None) -> UsageSnapshot:
        now = now or datetime.now(timezone.utc)
        cached = await self.cache.get_json(self._key(user_id, now))
        if cached:
            return UsageSnapshot(cached["requests_today"], cached["tokens_this_month"])

        requests_today = await self.db.scalar(
            select(func.count()).select_from(UsageRecord).where(
                UsageRecord.user_id == user_id,
                UsageRecord.created_at >= day_start(now),
                UsageRecord.status.in_(BILLABLE),
            )
        )
        tokens_month = await self.db.scalar(
            select(func.coalesce(func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0)).where(
                UsageRecord.user_id == user_id,
                UsageRecord.created_at >= month_start(now),
                UsageRecord.status.in_(BILLABLE),
            )
        )
        snap = UsageSnapshot(int(requests_today or 0), int(tokens_month or 0))
        await self.cache.set_json(self._key(user_id, now), snap.__dict__, SNAPSHOT_TTL)
        return snap

    async def record(
        self, *, user_id: uuid.UUID, session_id: uuid.UUID | None, provider: str, model: str,
        input_tokens: int, output_tokens: int, status: str, latency_ms: int, error: str | None = None,
    ) -> None:
        self.db.add(UsageRecord(
            user_id=user_id, session_id=session_id, provider=provider, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens, status=status,
            latency_ms=latency_ms, error=(error or "")[:1000] or None,
        ))
        await self.db.commit()
        await self.invalidate(user_id)

    async def invalidate(self, user_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await self.cache.delete(self._key(user_id, now), f"billing:{user_id}")

    async def summary(self, user: User) -> dict:
        now = datetime.now(timezone.utc)
        plan = plan_for(user)
        snap = await self.snapshot(user.id, now)
        return {
            "plan": plan_dict(plan),
            "usage": {
                "requests_today": snap.requests_today,
                "daily_request_limit": plan.daily_request_limit,
                "tokens_this_month": snap.tokens_this_month,
                "monthly_token_limit": plan.monthly_token_limit,
                "resets_at": next_day(now).isoformat(),
            },
            "preferred_provider": user.preferred_provider,
        }

    async def history(self, user_id: uuid.UUID, days: int) -> dict:
        now = datetime.now(timezone.utc)
        since = day_start(now) - timedelta(days=days - 1)
        day = func.date(UsageRecord.created_at)
        rows = (
            await self.db.execute(
                select(
                    day.label("day"),
                    func.count().label("requests"),
                    func.coalesce(func.sum(UsageRecord.input_tokens + UsageRecord.output_tokens), 0).label("tokens"),
                )
                .where(UsageRecord.user_id == user_id, UsageRecord.created_at >= since)
                .group_by(day)
            )
        ).all()
        by_day = {str(r.day): (int(r.requests), int(r.tokens)) for r in rows}
        daily = []
        for offset in range(days):
            date = (since + timedelta(days=offset)).date().isoformat()
            requests, tokens = by_day.get(date, (0, 0))
            daily.append({"date": date, "requests": requests, "tokens": tokens})

        recent = (
            await self.db.scalars(
                select(UsageRecord).where(UsageRecord.user_id == user_id).order_by(UsageRecord.created_at.desc()).limit(20)
            )
        ).all()
        return {
            "daily": daily,
            "recent": [
                {
                    "id": str(r.id), "created_at": r.created_at.isoformat(), "provider": r.provider, "model": r.model,
                    "status": r.status, "tokens": r.input_tokens + r.output_tokens, "latency_ms": r.latency_ms,
                    "session_id": str(r.session_id) if r.session_id else None,
                }
                for r in recent
            ],
        }


def plan_dict(plan: PlanDef) -> dict:
    return {
        "id": plan.id, "name": plan.name, "price_cents": plan.price_cents,
        "daily_request_limit": plan.daily_request_limit, "monthly_token_limit": plan.monthly_token_limit,
        "allowed_providers": list(plan.allowed_providers), "can_switch_provider": plan.can_switch_provider,
        "max_input_chars": plan.max_input_chars,
    }
