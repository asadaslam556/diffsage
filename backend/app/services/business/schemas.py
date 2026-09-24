from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("That doesn't look like an email address.")
        return value


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    plan_id: str
    preferred_provider: str | None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserUpdate(BaseModel):
    preferred_provider: str | None = None


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    profile: str | None = None


class SessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    profile: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    provider: str | None
    model: str | None
    status: str
    created_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]


class DocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    chunk_count: int
    char_count: int
    created_at: datetime
