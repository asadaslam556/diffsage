"""Session and message queries. The agent service uses these too."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import Message
from app.core.errors import NotFound
from app.core.security import utcnow
from app.db.models import ChatMessage, ChatSession, Document


def title_from(text: str) -> str:
    # skip code fences, so pasting a ```diff block doesn't title the review "```diff"
    first = next((line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("```")), "New review")
    return first[:77] + "..." if len(first) > 80 else first


async def get_owned_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> ChatSession:
    session = await db.get(ChatSession, session_id)
    # same 404 whether it doesn't exist or belongs to someone else
    if session is None or session.user_id != user_id:
        raise NotFound("That conversation doesn't exist.", code="session_not_found")
    return session


async def get_or_create_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID | None, *, first_message: str, profile: str
) -> ChatSession:
    if session_id is not None:
        return await get_owned_session(db, user_id, session_id)
    session = ChatSession(user_id=user_id, title=title_from(first_message), profile=profile)
    db.add(session)
    await db.flush()
    return session


async def recent_history(db: AsyncSession, session_id: uuid.UUID, limit: int) -> list[Message]:
    rows = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.status != "error")
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [Message(role=row.role, content=row.content) for row in reversed(rows) if row.content.strip()]  # type: ignore[arg-type]


async def touch(db: AsyncSession, session: ChatSession) -> None:
    session.updated_at = utcnow()


async def tools_with_data(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, tools: tuple[str, ...]) -> tuple[str, ...]:
    """Drop tools that can only come back empty for this user.

    A lookup that returns "nothing uploaded" still costs a whole extra model
    round, which is a minute or more for a local model on a laptop CPU. Small
    models also call every tool they're offered, whether or not it makes sense.
    """
    keep = []
    for name in tools:
        if name == "search_guidelines":
            has = await db.scalar(select(Document.id).where(Document.user_id == user_id).limit(1))
        elif name == "get_past_reviews":
            has = await db.scalar(
                select(ChatMessage.id)
                .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(ChatSession.user_id == user_id, ChatSession.id != session_id, ChatMessage.role == "assistant")
                .limit(1)
            )
        else:
            has = True  # tools we know nothing about stay on
        if has:
            keep.append(name)
    return tuple(keep)
