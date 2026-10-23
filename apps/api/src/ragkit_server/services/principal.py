"""Who is calling: a signed-in person, or an API key bound to one project."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ragkit_server.core.security import SessionClaims
from ragkit_server.models import ApiKey, User


@dataclass(frozen=True, slots=True)
class Principal:
    user: User | None = None
    api_key: ApiKey | None = None
    session: SessionClaims | None = None
    via_cookie: bool = False

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def api_key_id(self) -> uuid.UUID | None:
        return self.api_key.id if self.api_key else None

    @property
    def rate_key(self) -> str:
        if self.api_key is not None:
            return f"key:{self.api_key.id}"
        return f"user:{self.user_id}"
