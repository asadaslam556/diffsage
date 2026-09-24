"""FastAPI dependencies shared by the service routers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.errors import AuthError
from app.db.models import User


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.sessionmaker() as session:
        yield session


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    # the gateway already validated the token; here we make sure the account still exists
    raw = getattr(request.state, "user_id", None)
    if not raw:
        raise AuthError("Sign in first.", code="missing_token")
    user = await db.get(User, uuid.UUID(raw))
    if user is None or not user.is_active:
        raise AuthError("This account doesn't exist or has been disabled.", code="account_inactive")
    return user
