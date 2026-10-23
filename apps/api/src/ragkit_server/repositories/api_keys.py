from __future__ import annotations

import uuid

from sqlalchemy import select

from ragkit_server.models import ApiKey
from ragkit_server.repositories.base import Repository


class ApiKeyRepository(Repository):
    async def by_prefix(self, prefix: str) -> ApiKey | None:
        result = await self.session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
        return result.scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def for_project(self, project_id: uuid.UUID) -> list[ApiKey]:
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.project_id == project_id).order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars())

    async def add(self, key: ApiKey) -> ApiKey:
        self.session.add(key)
        await self.session.flush()
        return key
