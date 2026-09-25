"""AI agent service endpoints.

Everything that can be rejected is rejected *before* the stream starts,
so the client gets a proper status code (402 over quota, 403 wrong plan,
422 bad input) instead of a 200 that turns into an error halfway through.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.gateway_client import GatewayClient
from app.agent.profiles import PROFILES, get_profile
from app.agent.runner import AgentRunner
from app.agent.tools import ToolContext, ToolExecutor
from app.agent.types import Message
from app.container import Container
from app.core.errors import ValidationFailed
from app.core.security import create_access_token
from app.db.models import ChatMessage, User
from app.services.agent.stream import chat_event_stream
from app.services.billing.policy import check_quota, pick_provider
from app.services.billing.service import BillingService, plan_for
from app.services.business.repository import get_or_create_session, recent_history, tools_with_data, touch
from app.services.deps import current_user, get_container, get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=200_000)
    session_id: uuid.UUID | None = None
    profile: str | None = None
    provider: str | None = None  # one-off override; otherwise the user's saved preference


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    settings = container.settings
    if not body.message.strip():
        raise ValidationFailed("The message is empty.", code="empty_message")

    plan = plan_for(user)
    provider = pick_provider(
        plan, body.provider or user.preferred_provider,
        default=settings.default_provider, fallback=settings.fallback_provider,
    )
    billing = BillingService(db, container.cache)
    check_quota(plan, await billing.snapshot(user.id), input_chars=len(body.message))

    session = await get_or_create_session(
        db, user.id, body.session_id,
        first_message=body.message, profile=body.profile or settings.default_profile,
    )
    profile = get_profile(body.profile or session.profile)
    if profile is None:
        raise ValidationFailed(f"Unknown profile '{body.profile}'.", code="unknown_profile")

    history = await recent_history(db, session.id, settings.history_messages)
    db.add(ChatMessage(session_id=session.id, role="user", content=body.message))
    await touch(db, session)
    await db.commit()
    history.append(Message(role="user", content=body.message))

    # short-lived token so the agent's tools can call back through the gateway as this user
    agent_token = create_access_token(user.id, settings.jwt_secret, minutes=5, scope="agent")
    gateway = GatewayClient(settings.internal_gateway_url, agent_token, transport=container.gateway_transport)
    tools = await tools_with_data(db, user.id, session.id, profile.tools)
    withheld = tuple(t for t in profile.tools if t not in tools)
    executor = ToolExecutor(tools, ToolContext(str(user.id), str(session.id), gateway), withheld=withheld)
    runner = AgentRunner(container.router, executor, max_rounds=settings.max_tool_rounds, allow_provider=plan.allows_provider)

    log.info("chat start session=%s provider=%s profile=%s chars=%d", session.id, provider, profile.name, len(body.message))
    stream = chat_event_stream(
        container=container, runner=runner, history=history, system=profile.system_prompt,
        user_id=user.id, session_id=session.id, provider=provider, profile=profile.name,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/providers")
async def list_providers(user: User = Depends(current_user), container: Container = Depends(get_container)) -> dict:
    plan = plan_for(user)
    health = container.health_cache.get("providers", {}).get("data", {})
    return {
        # what this user gets without picking: the server default if their plan allows it
        "default": pick_default(plan, container),
        "fallback": container.settings.fallback_provider,
        # what this user actually falls back to, in order (plans skip providers they lack)
        "fallbacks": [n for n in container.settings.fallback_chain if plan.allows_provider(n)],
        "selected": user.preferred_provider,
        "can_switch": plan.can_switch_provider,
        "providers": [
            {
                **p.describe(),
                "allowed_on_plan": plan.can_switch_provider and plan.allows_provider(name) or name == pick_default(plan, container),
                "health": health.get(name),
            }
            for name, p in container.providers.items()
        ],
    }


def pick_default(plan, container: Container) -> str:
    s = container.settings
    return pick_provider(plan, None, default=s.default_provider, fallback=s.fallback_provider)


@router.get("/profiles")
async def list_profiles() -> list[dict]:
    return [
        {"name": p.name, "title": p.title, "description": p.description, "input_hint": p.input_hint, "tools": list(p.tools)}
        for p in PROFILES.values()
    ]
