"""Projects, membership and access resolution."""

from __future__ import annotations

import secrets
import uuid

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnprocessableError,
)
from ragkit_server.core.logging import get_logger
from ragkit_server.core.security import hash_password
from ragkit_server.ingestion.sniff import slugify
from ragkit_server.models import AuditEvent, Membership, Project, User
from ragkit_server.models.enums import Role
from ragkit_server.repositories.audit import AuditRepository
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.repositories.projects import ProjectRepository, ProjectSummary
from ragkit_server.repositories.users import UserRepository
from ragkit_server.services import audit
from ragkit_server.services.auth import temporary_password
from ragkit_server.services.container import Container
from ragkit_server.services.principal import Principal

log = get_logger("ragkit.projects")


class ProjectService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    async def resolve(self, principal: Principal, ref: str) -> tuple[Project, Role]:
        """The project and the caller's role in it. Non-members get 404, not 403."""
        project = await self._by_ref(ref)
        if project is None:
            raise NotFoundError("Project not found.")
        if principal.api_key is not None:
            if principal.api_key.project_id != project.id:
                raise NotFoundError("Project not found.")
            return project, Role(principal.api_key.role)
        if principal.user is None:
            raise NotFoundError("Project not found.")
        membership = await self.projects.membership(project.id, principal.user.id)
        if membership is None:
            raise NotFoundError("Project not found.")
        return project, Role(membership.role)

    async def _by_ref(self, ref: str) -> Project | None:
        try:
            return await self.projects.get(uuid.UUID(ref))
        except ValueError:
            return await self.projects.by_slug(ref.lower())

    async def list_for(self, user: User) -> list[ProjectSummary]:
        return await self.projects.for_user(user.id)

    async def create(self, principal: Principal, name: str, description: str = "") -> Project:
        if principal.user is None:
            raise ForbiddenError("Only people can create projects.")
        base = slugify(name, limit=48, fallback="project")
        slug = base
        while await self.projects.slug_taken(slug):
            slug = f"{base}-{secrets.token_hex(2)}"
        project = await self.projects.add(
            Project(
                slug=slug,
                name=name.strip(),
                description=description.strip(),
                created_by=principal.user.id,
            )
        )
        await self.projects.add_member(project.id, principal.user.id, Role.OWNER)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="project.created",
            target_type="project",
            target_id=project.id,
            details={"name": project.name},
        )
        await self.session.commit()
        return project

    async def update(
        self, project: Project, principal: Principal, *, name: str | None, description: str | None
    ) -> Project:
        changed: dict[str, object] = {}
        if name is not None and name.strip() != project.name:
            project.name = name.strip()
            changed["name"] = project.name
        if description is not None and description.strip() != project.description:
            project.description = description.strip()
            changed["description"] = True
        if changed:
            await audit.record(
                self.session,
                project_id=project.id,
                principal=principal,
                action="project.updated",
                target_type="project",
                target_id=project.id,
                details=changed,
            )
            await self.session.commit()
        return project

    async def delete(self, project: Project) -> None:
        keys = await DocumentRepository(self.session).storage_keys_for_project(project.id)
        await self.session.delete(project)
        await self.session.commit()
        # Rows are gone with the commit; the files follow. A failure here only leaves
        # unreachable objects behind, which bucket lifecycle rules can expire.
        for key in keys:
            try:
                await self.c.storage.delete(key)
            except Exception:
                log.warning("storage_delete_failed", key=key)

    async def members(self, project_id: uuid.UUID) -> list[tuple[Membership, User]]:
        return await self.projects.members(project_id)

    async def add_member(
        self, project: Project, principal: Principal, email: str, name: str | None, role: Role
    ) -> tuple[Membership, User, str | None]:
        user = await self.users.by_email(email)
        password: str | None = None
        if user is None:
            password = temporary_password()
            user = await self.users.add(
                User(
                    email=email.strip().lower(),
                    name=(name or email.split("@")[0]).strip()[:120],
                    password_hash=await anyio.to_thread.run_sync(hash_password, password),
                )
            )
        elif await self.projects.membership(project.id, user.id):
            raise ConflictError("That person is already a member.")
        membership = await self.projects.add_member(project.id, user.id, role)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="member.added",
            target_type="user",
            target_id=user.id,
            details={
                "email": user.email,
                "role": role.value,
                "account_created": password is not None,
            },
        )
        await self.session.commit()
        return membership, user, password

    async def change_role(
        self, project: Project, principal: Principal, user_id: uuid.UUID, role: Role
    ) -> tuple[Membership, User]:
        membership = await self.projects.membership(project.id, user_id)
        user = await self.users.get(user_id)
        if membership is None or user is None:
            raise NotFoundError("That person is not a member.")
        if membership.role == Role.OWNER and role != Role.OWNER:
            await self._keep_an_owner(project.id)
        membership.role = role.value
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="member.role_changed",
            target_type="user",
            target_id=user_id,
            details={"role": role.value},
        )
        await self.session.commit()
        return membership, user

    async def remove_member(
        self, project: Project, principal: Principal, user_id: uuid.UUID
    ) -> None:
        membership = await self.projects.membership(project.id, user_id)
        if membership is None:
            raise NotFoundError("That person is not a member.")
        if membership.role == Role.OWNER:
            await self._keep_an_owner(project.id)
        await self.session.delete(membership)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="member.removed",
            target_type="user",
            target_id=user_id,
        )
        await self.session.commit()

    async def activity(
        self, project_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[tuple[AuditEvent, str | None]], int]:
        return await AuditRepository(self.session).recent(project_id, limit=limit, offset=offset)

    async def _keep_an_owner(self, project_id: uuid.UUID) -> None:
        if await self.projects.owner_count(project_id) <= 1:
            raise UnprocessableError("A project needs at least one owner.", code="last_owner")


def require_role(role: Role, required: Role) -> None:
    if not role.allows(required):
        raise ForbiddenError(f"This needs the {required.value} role in this project.")
