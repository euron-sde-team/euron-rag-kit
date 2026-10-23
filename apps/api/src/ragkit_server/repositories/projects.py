from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from ragkit_server.models import Collection, Membership, Project, User
from ragkit_server.models.enums import Role
from ragkit_server.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    project: Project
    role: str
    collection_count: int
    member_count: int


class ProjectRepository(Repository):
    async def get(self, project_id: uuid.UUID) -> Project | None:
        return await self.session.get(Project, project_id)

    async def by_slug(self, slug: str) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.slug == slug))
        return result.scalar_one_or_none()

    async def slug_taken(self, slug: str) -> bool:
        return bool(await self.session.scalar(select(func.count()).where(Project.slug == slug)))

    async def add(self, project: Project) -> Project:
        self.session.add(project)
        await self.session.flush()
        return project

    async def membership(self, project_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
        return await self.session.get(Membership, (project_id, user_id))

    async def for_user(self, user_id: uuid.UUID) -> list[ProjectSummary]:
        collections = (
            select(func.count())
            .where(Collection.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        # The outer query joins memberships too; counting through an alias keeps the
        # subquery from correlating to the caller's own membership row.
        everyone = aliased(Membership)
        members = (
            select(func.count())
            .select_from(everyone)
            .where(everyone.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Project, Membership.role, collections, members)
            .join(Membership, Membership.project_id == Project.id)
            .where(Membership.user_id == user_id)
            .order_by(Project.name)
        )
        return [ProjectSummary(p, role, c, m) for p, role, c, m in result.all()]

    async def members(self, project_id: uuid.UUID) -> list[tuple[Membership, User]]:
        result = await self.session.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.project_id == project_id)
            .order_by(Membership.created_at)
        )
        return [(m, u) for m, u in result.all()]

    async def owner_count(self, project_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(
                    Membership.project_id == project_id, Membership.role == Role.OWNER
                )
            )
            or 0
        )

    async def add_member(self, project_id: uuid.UUID, user_id: uuid.UUID, role: Role) -> Membership:
        membership = Membership(project_id=project_id, user_id=user_id, role=role.value)
        self.session.add(membership)
        await self.session.flush()
        return membership
