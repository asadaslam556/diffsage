from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Plan
from app.services.billing.plans import PLANS


def create_engine(url: str) -> AsyncEngine:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs.update(pool_size=10, max_overflow=10)
    return create_async_engine(url, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False so objects stay usable after commit inside a request
    return async_sessionmaker(engine, expire_on_commit=False)


async def sync_plans(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Upsert the plan table from app.services.billing.plans."""
    async with sessionmaker() as session:
        existing = {p.id: p for p in (await session.scalars(select(Plan))).all()}
        for plan in PLANS.values():
            row = existing.get(plan.id) or Plan(id=plan.id)
            row.name = plan.name
            row.price_cents = plan.price_cents
            row.daily_request_limit = plan.daily_request_limit
            row.monthly_token_limit = plan.monthly_token_limit
            row.allowed_providers = list(plan.allowed_providers)
            row.can_switch_provider = plan.can_switch_provider
            row.max_input_chars = plan.max_input_chars
            session.add(row)
        await session.commit()


async def ping(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
