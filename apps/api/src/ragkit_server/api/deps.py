"""Request dependencies: infrastructure, the caller, project access and rate limits."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.core.config import Settings
from ragkit_server.core.errors import ForbiddenError, RateLimitedError, UnauthorizedError
from ragkit_server.core.logging import get_logger
from ragkit_server.core.security import API_KEY_PREFIX
from ragkit_server.models import Collection, Project, User
from ragkit_server.models.enums import Role
from ragkit_server.services.api_keys import ApiKeyService
from ragkit_server.services.auth import SESSION_COOKIE, AuthService
from ragkit_server.services.collections import CollectionService
from ragkit_server.services.container import Container
from ragkit_server.services.principal import Principal
from ragkit_server.services.projects import ProjectService, require_role

log = get_logger("ragkit.api")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.db.session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _origin_allowed(request: Request, settings: Settings) -> bool:
    """CSRF defence for cookie sessions: unsafe methods must come from our own web app."""
    origin = request.headers.get("origin")
    if origin is None and (referer := request.headers.get("referer")):
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    allowed = {*settings.cors_origins, settings.web_url.rstrip("/")}
    return origin in allowed


async def get_principal(
    request: Request, container: ContainerDep, session: SessionDep
) -> Principal:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token.startswith(f"{API_KEY_PREFIX}_"):
            return Principal(api_key=await ApiKeyService(container, session).resolve(token))
        user, claims = await AuthService(container, session).resolve(token)
        return Principal(user=user, session=claims)
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        user, claims = await AuthService(container, session).resolve(cookie)
        if request.method not in _SAFE_METHODS and not _origin_allowed(request, container.settings):
            raise ForbiddenError("Cross-site request blocked.", code="csrf")
        return Principal(user=user, session=claims, via_cookie=True)
    raise UnauthorizedError()


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_user(principal: PrincipalDep) -> User:
    if principal.user is None:
        raise ForbiddenError("This needs a signed-in person, not an API key.")
    return principal.user


UserDep = Annotated[User, Depends(get_user)]


@dataclass(frozen=True, slots=True)
class ProjectContext:
    project: Project
    role: Role
    principal: Principal

    @property
    def id(self) -> uuid.UUID:
        return self.project.id


class ProjectAccess:
    """Resolve `{project}` (id or slug) and require at least `minimum` role in it."""

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    async def __call__(
        self,
        project: Annotated[str, Path(description="Project id or slug.", max_length=64)],
        principal: PrincipalDep,
        container: ContainerDep,
        session: SessionDep,
    ) -> ProjectContext:
        resolved, role = await ProjectService(container, session).resolve(principal, project)
        require_role(role, self.minimum)
        return ProjectContext(resolved, role, principal)


ViewerDep = Annotated[ProjectContext, Depends(ProjectAccess(Role.VIEWER))]
EditorDep = Annotated[ProjectContext, Depends(ProjectAccess(Role.EDITOR))]
OwnerDep = Annotated[ProjectContext, Depends(ProjectAccess(Role.OWNER))]


@dataclass(frozen=True, slots=True)
class CollectionContext:
    project: Project
    collection: Collection
    role: Role
    principal: Principal


class CollectionAccess:
    """`{project}` and `{collection}` together: the collection is looked up inside the
    caller's project only, so an id from another project resolves to nothing."""

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    async def __call__(
        self,
        project: Annotated[str, Path(description="Project id or slug.", max_length=64)],
        collection: Annotated[str, Path(description="Collection id or slug.", max_length=64)],
        principal: PrincipalDep,
        container: ContainerDep,
        session: SessionDep,
    ) -> CollectionContext:
        resolved, role = await ProjectService(container, session).resolve(principal, project)
        require_role(role, self.minimum)
        found = await CollectionService(container, session).get(resolved, collection)
        return CollectionContext(resolved, found, role, principal)


CollectionViewerDep = Annotated[CollectionContext, Depends(CollectionAccess(Role.VIEWER))]
CollectionEditorDep = Annotated[CollectionContext, Depends(CollectionAccess(Role.EDITOR))]
CollectionOwnerDep = Annotated[CollectionContext, Depends(CollectionAccess(Role.OWNER))]


def rate_limit(bucket: str, setting: str) -> Callable[..., Awaitable[None]]:
    async def dependency(
        response: Response, principal: PrincipalDep, container: ContainerDep
    ) -> None:
        try:
            result = await container.limiter.hit(
                f"{bucket}:{principal.rate_key}", getattr(container.settings, setting)
            )
        except Exception:
            # Serving stays up when Valkey is down: the request passes uncounted rather
            # than failing. Sign-in is the exception and fails closed (routes/auth.py).
            log.warning("rate_limit_unavailable", bucket=bucket)
            return
        response.headers.update(result.headers())
        if not result.allowed:
            raise RateLimitedError(headers={"retry-after": str(result.reset_s), **result.headers()})

    return dependency


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
