"""Project API keys: create, list, revoke, and resolve on every keyed request."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.core.errors import NotFoundError, UnauthorizedError
from ragkit_server.core.logging import get_logger
from ragkit_server.core.security import generate_api_key, parse_api_key, verify_api_key_secret
from ragkit_server.models import ApiKey, Project
from ragkit_server.repositories.api_keys import ApiKeyRepository
from ragkit_server.services import audit
from ragkit_server.services.container import Container
from ragkit_server.services.principal import Principal

log = get_logger("ragkit.api_keys")

_TOUCH_INTERVAL_S = 60


class ApiKeyService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.keys = ApiKeyRepository(session)

    @property
    def _pepper(self) -> str:
        return self.c.settings.api_key_pepper.get_secret_value()

    async def create(
        self,
        project: Project,
        principal: Principal,
        name: str,
        role: str,
        expires_in_days: int | None,
    ) -> tuple[ApiKey, str]:
        generated = generate_api_key(self._pepper)
        key = await self.keys.add(
            ApiKey(
                project_id=project.id,
                created_by=principal.user_id,
                name=name.strip(),
                prefix=generated.prefix,
                secret_hash=generated.secret_hash,
                role=role,
                expires_at=(
                    datetime.now(UTC) + timedelta(days=expires_in_days) if expires_in_days else None
                ),
            )
        )
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="api_key.created",
            target_type="api_key",
            target_id=key.id,
            details={"name": key.name, "role": role, "prefix": key.prefix},
        )
        await self.session.commit()
        return key, generated.plaintext

    async def for_project(self, project_id: uuid.UUID) -> list[ApiKey]:
        return await self.keys.for_project(project_id)

    async def revoke(self, project: Project, principal: Principal, key_id: uuid.UUID) -> ApiKey:
        key = await self.keys.get(project.id, key_id)
        if key is None:
            raise NotFoundError("API key not found.")
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            await audit.record(
                self.session,
                project_id=project.id,
                principal=principal,
                action="api_key.revoked",
                target_type="api_key",
                target_id=key.id,
                details={"name": key.name, "prefix": key.prefix},
            )
            await self.session.commit()
        return key

    async def resolve(self, raw: str) -> ApiKey:
        parsed = parse_api_key(raw)
        if parsed is None:
            raise UnauthorizedError("That API key is not valid.", code="invalid_api_key")
        prefix, secret = parsed
        key = await self.keys.by_prefix(prefix)
        if key is None or not verify_api_key_secret(secret, key.secret_hash, self._pepper):
            raise UnauthorizedError("That API key is not valid.", code="invalid_api_key")
        now = datetime.now(UTC)
        if key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
            raise UnauthorizedError(
                "That API key has been revoked or has expired.", code="invalid_api_key"
            )
        # Record use at most once a minute per key, so busy keys do not write on every call.
        # Without Valkey the key still works; only the last-used time is not updated.
        try:
            first_this_minute = await self.c.redis.set(
                f"apikey:touched:{key.id}", b"1", ex=_TOUCH_INTERVAL_S, nx=True
            )
        except Exception:
            log.warning("api_key_touch_skipped", key_id=str(key.id))
            return key
        if first_this_minute:
            key.last_used_at = now
            await self.session.commit()
        return key
