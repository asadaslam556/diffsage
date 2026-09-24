"""What gets written when a stream ends early."""

import uuid

from sqlalchemy import select

from app.db.models import ChatMessage, ChatSession, User
from app.services.agent.stream import StreamState, _persist


async def test_a_stream_stopped_before_any_text_still_leaves_a_reply_row(container):
    async with container.sessionmaker() as db:
        user = User(email="stop@example.com", password_hash="x", plan_id="free")
        db.add(user)
        await db.flush()
        session = ChatSession(user_id=user.id, title="t", profile="code_reviewer")
        db.add(session)
        await db.commit()
        user_id, session_id = user.id, session.id

    message_id = uuid.uuid4()
    await _persist(container, StreamState(provider="ollama", status="cancelled"), user_id, session_id, message_id, 100, 5)

    async with container.sessionmaker() as db:
        row = await db.scalar(select(ChatMessage).where(ChatMessage.id == message_id))
    # without this row the history showed a question with nothing after it
    assert row is not None and row.status == "cancelled" and row.content == ""
