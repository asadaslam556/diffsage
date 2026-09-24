"""Password hashing and tokens.

Passwords: PBKDF2-SHA256 from the stdlib, 600k iterations (OWASP's current
number). Stored as "pbkdf2_sha256$iterations$salt$hash" so the iteration
count can go up later without breaking old hashes.

Access tokens are short-lived JWTs. Refresh tokens are opaque random strings;
only their sha256 lands in the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.core.errors import AuthError

_ALGO = "pbkdf2_sha256"
_ISSUER = "diffsage"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, iterations: int = 600_000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_ALGO}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
        expected_digest = _unb64(expected)
    except (ValueError, TypeError):
        # a mangled hash in the db shouldn't turn into a 500 on login
        # (binascii.Error from a bad base64 tail is a ValueError too)
        return False
    return hmac.compare_digest(digest, expected_digest)


def needs_rehash(stored: str, iterations: int) -> bool:
    try:
        return int(stored.split("$")[1]) < iterations
    except (IndexError, ValueError):
        return True


def burn_password_check(password: str, iterations: int) -> None:
    # run on "no such email" so it takes as long as "wrong password"
    hashlib.pbkdf2_hmac("sha256", password.encode(), b"x" * 16, iterations)


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    scope: str
    expires_at: datetime


def create_access_token(
    user_id: uuid.UUID | str,
    secret: str,
    *,
    minutes: int,
    scope: str = "user",
    algorithm: str = "HS256",
) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "scope": scope,
        "iss": _ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(claims, secret, algorithm=algorithm)


def decode_access_token(token: str, secret: str, algorithm: str = "HS256") -> TokenPayload:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            issuer=_ISSUER,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Your session expired. Sign in again.", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid access token.", code="invalid_token") from exc
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AuthError("Invalid access token.", code="invalid_token") from exc
    return TokenPayload(
        user_id=user_id,
        scope=str(claims.get("scope", "user")),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
    )


def new_refresh_token() -> tuple[str, str]:
    """Returns (token to hand the client, hash to store)."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes even for timezone=True columns
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
