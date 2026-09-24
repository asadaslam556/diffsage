"""Core app endpoints: the account, conversations, uploaded guidelines.

The last two routes (document search, recent reviews) are what the agent's
tools call when they come back in through the gateway.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.profiles import PROFILES
from app.container import Container
from app.core.errors import NotFound, PermissionDenied, ServiceUnavailable, ValidationFailed
from app.db.models import ChatMessage, ChatSession, Document, User
from app.services.billing.service import plan_for
from app.services.business.auth_router import user_out
from app.services.business.repository import get_owned_session, touch
from app.services.business.schemas import (
    DocumentCreate, DocumentOut, MessageOut, SessionCreate, SessionDetail, SessionOut, SessionUpdate, UserOut, UserUpdate,
)
from app.services.deps import current_user, get_container, get_db
from app.vectorstore.embeddings import chunk_text
from app.vectorstore.store import VectorStoreError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/app", tags=["app"])


# --- account ----------------------------------------------------------------

@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return user_out(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> UserOut:
    name = body.preferred_provider
    if name is not None:
        plan = plan_for(user)
        provider = container.providers.get(name)
        if provider is None:
            raise ValidationFailed(f"There's no provider called '{name}'.", code="unknown_provider")
        if not plan.can_switch_provider or not plan.allows_provider(name):
            raise PermissionDenied(f"The {plan.name} plan can't switch providers. Upgrade to Pro.", code="provider_not_in_plan")
        if not provider.is_configured():
            raise ValidationFailed(f"{name} isn't set up on this server yet (missing API key).", code="provider_not_configured")
    user.preferred_provider = name
    await db.commit()
    await container.cache.delete(f"billing:{user.id}")
    return user_out(user)


# --- conversations ------------------------------------------------------------

def _session_out(s: ChatSession) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, profile=s.profile, created_at=s.created_at, updated_at=s.updated_at)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    rows = await db.scalars(
        select(ChatSession).where(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).limit(limit)
    )
    return [_session_out(s) for s in rows.all()]


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> SessionOut:
    profile = body.profile or container.settings.default_profile
    if profile not in PROFILES:
        raise ValidationFailed(f"Unknown profile '{profile}'.", code="unknown_profile")
    session = ChatSession(user_id=user.id, title=body.title or "New review", profile=profile)
    db.add(session)
    await db.commit()
    return _session_out(session)


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    session = await get_owned_session(db, user.id, session_id)
    messages = (
        await db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at))
    ).all()
    return SessionDetail(
        **_session_out(session).model_dump(),
        messages=[
            MessageOut(id=m.id, role=m.role, content=m.content, provider=m.provider, model=m.model, status=m.status, created_at=m.created_at)
            for m in messages
        ],
    )


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: uuid.UUID, body: SessionUpdate,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
) -> SessionOut:
    session = await get_owned_session(db, user.id, session_id)
    session.title = body.title.strip()
    await touch(db, session)
    await db.commit()
    return _session_out(session)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
) -> Response:
    session = await get_owned_session(db, user.id, session_id)
    # explicit delete of messages so this works on SQLite without FK pragmas too
    await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session.id))
    await db.delete(session)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- guidelines (RAG) ---------------------------------------------------------

def _document_out(d: Document) -> DocumentOut:
    return DocumentOut(id=d.id, filename=d.filename, chunk_count=d.chunk_count, char_count=d.char_count, created_at=d.created_at)


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> list[DocumentOut]:
    rows = await db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc()))
    return [_document_out(d) for d in rows.all()]


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    body: DocumentCreate,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> DocumentOut:
    chunks = chunk_text(body.content)
    if not chunks:
        raise ValidationFailed("That file is empty.", code="empty_document")
    if len(chunks) > 400:
        raise ValidationFailed("That file is too big to index. Split it up.", code="document_too_large")
    try:
        vectors = await container.embedder.embed(chunks)
    except Exception as exc:  # noqa: BLE001 - provider down, wrong model, dim mismatch...
        log.warning("embedding failed for upload: %s", exc)
        raise ServiceUnavailable("Couldn't index the file: the embedding model isn't available. Try again in a minute.", code="embedding_failed") from exc

    document = Document(user_id=user.id, filename=body.filename, chunk_count=len(chunks), char_count=len(body.content))
    db.add(document)
    await db.flush()
    try:
        await container.vector_store.upsert(str(user.id), str(document.id), body.filename, chunks, vectors)
    except VectorStoreError as exc:
        await db.rollback()
        log.error("vector upsert failed: %s", exc)
        raise ServiceUnavailable("The search index is unavailable right now. Try again in a minute.", code="vectorstore_down") from exc
    await db.commit()
    return _document_out(document)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
    container: Container = Depends(get_container),
) -> Response:
    document = await db.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise NotFound("That document doesn't exist.", code="document_not_found")
    try:
        await container.vector_store.delete_document(str(user.id), str(document.id))
    except VectorStoreError as exc:
        raise ServiceUnavailable("The search index is unavailable right now. Try again in a minute.", code="vectorstore_down") from exc
    await db.delete(document)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/search")
async def search_documents(
    q: str = Query(min_length=1, max_length=500),
    k: int = Query(4, ge=1, le=8),
    user: User = Depends(current_user),
    container: Container = Depends(get_container),
) -> dict:
    try:
        [vector] = await container.embedder.embed([q])
        hits = await container.vector_store.search(str(user.id), vector, k)
    except VectorStoreError as exc:
        raise ServiceUnavailable("The search index is unavailable right now.", code="vectorstore_down") from exc
    except Exception as exc:  # noqa: BLE001
        log.warning("embedding failed for search: %s", exc)
        raise ServiceUnavailable("Search failed: the embedding model isn't available.", code="embedding_failed") from exc
    return {"results": [{"text": h.text, "score": h.score, "filename": h.filename, "document_id": h.document_id} for h in hits]}


@router.get("/reviews/recent")
async def recent_reviews(
    limit: int = Query(3, ge=1, le=5),
    exclude_session: uuid.UUID | None = None,
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db),
) -> dict:
    query = (
        select(ChatMessage, ChatSession.title)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatSession.user_id == user.id, ChatMessage.role == "assistant", ChatMessage.status != "error")
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    if exclude_session is not None:
        query = query.where(ChatMessage.session_id != exclude_session)
    rows = (await db.execute(query)).all()
    return {
        "reviews": [
            {"session_title": title, "created_at": str(msg.created_at), "excerpt": msg.content[:1200]}
            for msg, title in rows
        ]
    }


@router.get("/stats")
async def stats(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)) -> dict:
    sessions = await db.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user.id))
    documents = await db.scalar(select(func.count()).select_from(Document).where(Document.user_id == user.id))
    return {"sessions": sessions or 0, "documents": documents or 0}
