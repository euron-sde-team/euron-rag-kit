from __future__ import annotations

import uuid

from sqlalchemy import func, select

from ragkit_server.models import ApiKey, AuditEvent, User
from ragkit_server.repositories.base import Repository


class AuditRepository(Repository):
    async def add(self, event: AuditEvent) -> None:
        self.session.add(event)

    async def recent(
        self, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[tuple[AuditEvent, str | None]], int]:
        total = int(
            await self.session.scalar(
                select(func.count()).where(AuditEvent.project_id == project_id)
            )
            or 0
        )
        result = await self.session.execute(
            select(AuditEvent, func.coalesce(User.name, ApiKey.name))
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .outerjoin(ApiKey, ApiKey.id == AuditEvent.actor_api_key_id)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(event, actor) for event, actor in result.all()], total
