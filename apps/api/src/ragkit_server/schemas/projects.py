from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field

from ragkit_server.schemas.common import ApiModel, StrictModel


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class ProjectUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class ProjectOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    role: str
    created_at: datetime


class MemberOut(ApiModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    joined_at: datetime


class MemberAdd(StrictModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)
    role: Literal["owner", "editor", "viewer"] = "viewer"


class MemberAdded(ApiModel):
    member: MemberOut
    temporary_password: str | None = Field(
        default=None, description="Set only when the account was created by this call. Shown once."
    )


class MemberUpdate(StrictModel):
    role: Literal["owner", "editor", "viewer"]


class AuditEventOut(ApiModel):
    id: uuid.UUID
    action: str
    target_type: str
    target_id: str | None
    details: dict[str, Any]
    actor: str | None = Field(default=None, description="Name of the person or API key.")
    created_at: datetime
