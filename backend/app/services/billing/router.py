from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.errors import AppError, ValidationFailed
from app.db.models import User
from app.services.billing.plans import PLANS
from app.services.billing.service import BillingService, plan_dict, plan_for
from app.services.deps import current_user, get_container, get_db

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlanChange(BaseModel):
    plan_id: str


class NotImplementedYet(AppError):
    status_code = 501
    code = "billing_not_configured"


@router.get("/plans")
async def list_plans() -> list[dict]:
    return [plan_dict(p) for p in PLANS.values()]


@router.get("/me")
async def my_billing(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> dict:
    return await BillingService(db, container.cache).summary(user)


@router.get("/usage")
async def usage_history(
    days: int = Query(14, ge=1, le=90),
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> dict:
    return await BillingService(db, container.cache).history(user.id, days)


@router.post("/plan")
async def change_plan(
    body: PlanChange,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> dict:
    # In production this endpoint would create a Stripe Checkout session and the
    # plan would flip in the webhook handler once payment clears. For local dev
    # and demos it just switches the plan so every tier can be tried.
    if not container.settings.billing_self_serve:
        raise NotImplementedYet("Plan changes go through checkout, which isn't wired up on this server.")
    if body.plan_id not in PLANS:
        raise ValidationFailed(f"Unknown plan '{body.plan_id}'.", code="unknown_plan")
    user.plan_id = body.plan_id
    new_plan = plan_for(user)
    # a provider you were allowed yesterday might not be allowed on the new plan
    if user.preferred_provider and not (new_plan.can_switch_provider and new_plan.allows_provider(user.preferred_provider)):
        user.preferred_provider = None
    await db.commit()
    service = BillingService(db, container.cache)
    await service.invalidate(user.id)
    return await service.summary(user)
