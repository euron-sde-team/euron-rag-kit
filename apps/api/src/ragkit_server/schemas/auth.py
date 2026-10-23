from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from ragkit_server.schemas.common import ApiModel, StrictModel


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class SignupRequest(StrictModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class UserOut(ApiModel):
    id: uuid.UUID
    email: str
    name: str
    is_admin: bool


class SessionOut(ApiModel):
    user: UserOut
    token: str = Field(description="Also set as an httponly cookie; use either.")
    expires_at: datetime


class ProjectSummaryOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    role: str
    collection_count: int
    member_count: int


class MeOut(ApiModel):
    user: UserOut
    projects: list[ProjectSummaryOut]


class ProfileUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=120)


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
