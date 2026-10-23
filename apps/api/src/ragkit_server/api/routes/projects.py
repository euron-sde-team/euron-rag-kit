"""Projects, members and the activity trail."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from ragkit_server.api.deps import (
    ContainerDep,
    OwnerDep,
    PrincipalDep,
    SessionDep,
    UserDep,
    ViewerDep,
)
from ragkit_server.models import Project
from ragkit_server.models.enums import Role
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.projects import (
    AuditEventOut,
    MemberAdd,
    MemberAdded,
    MemberOut,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from ragkit_server.services.projects import ProjectService

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def project_out(project: Project, role: str) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        role=role,
        created_at=project.created_at,
    )


@router.get("", summary="Projects you belong to")
async def list_projects(
    user: UserDep, container: ContainerDep, session: SessionDep
) -> list[ProjectOut]:
    summaries = await ProjectService(container, session).list_for(user)
    return [project_out(s.project, s.role) for s in summaries]


@router.post("", summary="Create a project", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, principal: PrincipalDep, container: ContainerDep, session: SessionDep
) -> ProjectOut:
    project = await ProjectService(container, session).create(
        principal, body.name, body.description
    )
    return project_out(project, Role.OWNER.value)


@router.get("/{project}", summary="A project and your role in it")
async def get_project(ctx: ViewerDep) -> ProjectOut:
    return project_out(ctx.project, ctx.role.value)


@router.patch("/{project}", summary="Rename or describe a project")
async def update_project(
    body: ProjectUpdate, ctx: OwnerDep, container: ContainerDep, session: SessionDep
) -> ProjectOut:
    project = await ProjectService(container, session).update(
        ctx.project, ctx.principal, name=body.name, description=body.description
    )
    return project_out(project, ctx.role.value)


@router.delete("/{project}", summary="Delete a project and everything in it", status_code=204)
async def delete_project(ctx: OwnerDep, container: ContainerDep, session: SessionDep) -> None:
    await ProjectService(container, session).delete(ctx.project)


@router.get("/{project}/members", summary="Members and their roles")
async def list_members(
    ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[MemberOut]:
    rows = await ProjectService(container, session).members(ctx.id)
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/{project}/members",
    summary="Add a member (creates the account if needed)",
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    body: MemberAdd, ctx: OwnerDep, container: ContainerDep, session: SessionDep
) -> MemberAdded:
    membership, user, password = await ProjectService(container, session).add_member(
        ctx.project, ctx.principal, body.email, body.name, Role(body.role)
    )
    return MemberAdded(
        member=MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=membership.role,
            joined_at=membership.created_at,
        ),
        temporary_password=password,
    )


@router.patch("/{project}/members/{user_id}", summary="Change a member's role")
async def change_role(
    user_id: uuid.UUID,
    body: MemberUpdate,
    ctx: OwnerDep,
    container: ContainerDep,
    session: SessionDep,
) -> MemberOut:
    membership, user = await ProjectService(container, session).change_role(
        ctx.project, ctx.principal, user_id, Role(body.role)
    )
    return MemberOut(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role,
        joined_at=membership.created_at,
    )


@router.delete("/{project}/members/{user_id}", summary="Remove a member", status_code=204)
async def remove_member(
    user_id: uuid.UUID, ctx: OwnerDep, container: ContainerDep, session: SessionDep
) -> None:
    await ProjectService(container, session).remove_member(ctx.project, ctx.principal, user_id)


@router.get("/{project}/activity", summary="Who changed what, newest first")
async def activity(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AuditEventOut]:
    events, total = await ProjectService(container, session).activity(
        ctx.id, limit=limit, offset=offset
    )
    return Page[AuditEventOut](
        items=[
            AuditEventOut(
                id=event.id,
                action=event.action,
                target_type=event.target_type,
                target_id=event.target_id,
                details=event.details,
                actor=actor,
                created_at=event.created_at,
            )
            for event, actor in events
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
