"""Collections: corpora with their own documents, pipeline versions and datasets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ragkit_server.api.deps import (
    CollectionEditorDep,
    CollectionOwnerDep,
    CollectionViewerDep,
    ContainerDep,
    EditorDep,
    SessionDep,
    ViewerDep,
    rate_limit,
)
from ragkit_server.schemas.collections import CollectionCreate, CollectionOut, CollectionUpdate
from ragkit_server.services.collections import CollectionService

router = APIRouter(prefix="/api/v1/projects/{project}/collections", tags=["collections"])


@router.get("", summary="Collections with document, version and chunk counts")
async def list_collections(
    ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[CollectionOut]:
    return await CollectionService(container, session).list(ctx.project)


@router.post(
    "",
    summary="Create a collection with its first pipeline version",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("ingest", "rate_limit_ingest"))],
)
async def create_collection(
    body: CollectionCreate, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> CollectionOut:
    service = CollectionService(container, session)
    collection = await service.create(ctx.project, ctx.principal, body)
    return await service.describe(ctx.project, collection)


@router.get("/{collection}", summary="A collection with its counts")
async def get_collection(
    ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> CollectionOut:
    return await CollectionService(container, session).describe(ctx.project, ctx.collection)


@router.patch("/{collection}", summary="Rename or describe a collection")
async def update_collection(
    body: CollectionUpdate, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> CollectionOut:
    service = CollectionService(container, session)
    await service.update(ctx.project, ctx.collection, ctx.principal, body)
    return await service.describe(ctx.project, ctx.collection)


@router.delete(
    "/{collection}",
    summary="Delete a collection with its documents, indexes, datasets and runs",
    status_code=204,
)
async def delete_collection(
    ctx: CollectionOwnerDep, container: ContainerDep, session: SessionDep
) -> None:
    await CollectionService(container, session).delete(ctx.project, ctx.collection, ctx.principal)
