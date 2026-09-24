"""Sign up, sign in, token refresh, sign out.

Access tokens live in memory on the client. The refresh token sits in an
httpOnly cookie scoped to /api/auth, so JavaScript can't read it and it's
only sent to these endpoints. Refresh tokens rotate on every use; reusing
an old one (outside a short grace period for two tabs racing) revokes the
whole lot for that user, since it usually means the token leaked.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.container import Container
from app.core.errors import AuthError, Conflict
from app.core.security import (
    as_utc,
    burn_password_check,
    create_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    utcnow,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.services.billing.plans import DEFAULT_PLAN
from app.services.business.schemas import Credentials, TokenResponse, UserOut
from app.services.deps import get_container, get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "ds_refresh"
REUSE_GRACE = timedelta(seconds=20)


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, plan_id=user.plan_id,
        preferred_provider=user.preferred_provider, created_at=user.created_at,
    )


async def _issue_tokens(db: AsyncSession, user: User, container: Container, response: Response) -> TokenResponse:
    settings = container.settings
    token, token_hash = new_refresh_token()
    db.add(RefreshToken(
        user_id=user.id, token_hash=token_hash,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
    ))
    await db.commit()
    response.set_cookie(
        REFRESH_COOKIE, token,
        max_age=settings.refresh_token_days * 86_400,
        httponly=True, secure=settings.is_production, samesite="lax", path="/api/auth",
    )
    return TokenResponse(
        access_token=create_access_token(user.id, settings.jwt_secret, minutes=settings.access_token_minutes),
        expires_in=settings.access_token_minutes * 60,
        user=user_out(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: Credentials, response: Response,
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container),
) -> TokenResponse:
    if await db.scalar(select(User.id).where(User.email == body.email)):
        raise Conflict("An account with that email already exists.", code="email_taken")
    password_hash = await run_in_threadpool(hash_password, body.password, container.settings.password_hash_iterations)
    user = User(email=body.email, password_hash=password_hash, plan_id=DEFAULT_PLAN)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:  # two signups with the same email at the same moment
        await db.rollback()
        raise Conflict("An account with that email already exists.", code="email_taken") from exc
    log.info("new account %s", user.id)
    return await _issue_tokens(db, user, container, response)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: Credentials, response: Response,
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container),
) -> TokenResponse:
    iterations = container.settings.password_hash_iterations
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        await run_in_threadpool(burn_password_check, body.password, iterations)
        raise AuthError("Wrong email or password.", code="bad_credentials")
    if not await run_in_threadpool(verify_password, body.password, user.password_hash):
        log.info("failed login for %s", user.id)
        raise AuthError("Wrong email or password.", code="bad_credentials")
    if not user.is_active:
        raise AuthError("This account has been disabled.", code="account_inactive")
    if needs_rehash(user.password_hash, iterations):
        user.password_hash = await run_in_threadpool(hash_password, body.password, iterations)
    return await _issue_tokens(db, user, container, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request, response: Response,
    db: AsyncSession = Depends(get_db), container: Container = Depends(get_container),
) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise AuthError("No active session.", code="no_refresh_token")
    row = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    now = utcnow()
    if row is None or as_utc(row.expires_at) < now:
        raise AuthError("Your session expired. Sign in again.", code="refresh_expired")
    if row.revoked_at is not None:
        if now - as_utc(row.revoked_at) > REUSE_GRACE:
            log.warning("refresh token reuse for user %s, revoking all their sessions", row.user_id)
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await db.commit()
        raise AuthError("Your session expired. Sign in again.", code="refresh_reused")

    row.revoked_at = now
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        await db.commit()
        raise AuthError("This account has been disabled.", code="account_inactive")
    return await _issue_tokens(db, user, container, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(token), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return response
