"""Project API keys (owner only), for applications, the SDK and CI."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from ragkit_server.api.deps import ContainerDep, OwnerDep, SessionDep
from ragkit_server.schemas.api_keys import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from ragkit_server.services.api_keys import ApiKeyService

router = APIRouter(prefix="/api/v1/projects/{project}/api-keys", tags=["api keys"])


@router.get("", summary="Keys for this project")
async def list_keys(ctx: OwnerDep, container: ContainerDep, session: SessionDep) -> list[ApiKeyOut]:
    keys = await ApiKeyService(container, session).for_project(ctx.id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post(
    "", summary="Create a key (the secret is shown once)", status_code=status.HTTP_201_CREATED
)
async def create_key(
    body: ApiKeyCreate, ctx: OwnerDep, container: ContainerDep, session: SessionDep
) -> ApiKeyCreated:
    key, plaintext = await ApiKeyService(container, session).create(
        ctx.project, ctx.principal, body.name, body.role, body.expires_in_days
    )
    return ApiKeyCreated.model_validate(
        {**ApiKeyOut.model_validate(key).model_dump(), "key": plaintext}
    )


@router.delete("/{key_id}", summary="Revoke a key", status_code=204)
async def revoke_key(
    key_id: uuid.UUID, ctx: OwnerDep, container: ContainerDep, session: SessionDep
) -> None:
    await ApiKeyService(container, session).revoke(ctx.project, ctx.principal, key_id)
