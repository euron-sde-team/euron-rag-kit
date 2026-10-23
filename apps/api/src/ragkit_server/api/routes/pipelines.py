"""Pipeline versions of a collection: create, activate, inspect chunks, preview."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from ragkit_server.api.deps import (
    CollectionEditorDep,
    CollectionViewerDep,
    ContainerDep,
    SessionDep,
)
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.pipelines import (
    ChunkOut,
    ChunkStats,
    PipelineCreate,
    PipelineVersionOut,
    PreviewOut,
    PreviewRequest,
)
from ragkit_server.services.pipelines import PipelineService

router = APIRouter(
    prefix="/api/v1/projects/{project}/collections/{collection}/pipelines", tags=["pipelines"]
)
VersionNumber = Annotated[int, Path(ge=1, description="Pipeline version number.")]


@router.get("", summary="Pipeline versions, newest first, with index build progress")
async def list_versions(
    ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> list[PipelineVersionOut]:
    return await PipelineService(container, session).list(ctx.collection)


@router.post(
    "",
    summary="Create a version (reuses the index when only retrieval or answering changed)",
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    body: PipelineCreate, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> PipelineVersionOut:
    service = PipelineService(container, session)
    version = await service.create(
        ctx.project,
        ctx.collection,
        ctx.principal,
        name=body.name,
        description=body.description,
        config=body.config,
        activate=body.activate,
    )
    return await service.detail(ctx.collection, version.version)


@router.post(
    "/preview",
    summary="Clean and chunk one document or some text with a candidate configuration",
)
async def preview(
    body: PreviewRequest, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> PreviewOut:
    return await PipelineService(container, session).preview(ctx.project, ctx.collection, body)


@router.get("/{version}", summary="A version with its configuration and index")
async def get_version(
    version: VersionNumber, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> PipelineVersionOut:
    return await PipelineService(container, session).detail(ctx.collection, version)


@router.post("/{version}/activate", summary="Serve queries with this version")
async def activate_version(
    version: VersionNumber, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> PipelineVersionOut:
    service = PipelineService(container, session)
    await service.activate(ctx.project, ctx.collection, ctx.principal, version)
    return await service.detail(ctx.collection, version)


@router.get("/{version}/chunks", summary="Browse the chunks of a version's index")
async def list_chunks(
    version: VersionNumber,
    ctx: CollectionViewerDep,
    container: ContainerDep,
    session: SessionDep,
    document_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ChunkOut]:
    return await PipelineService(container, session).chunk_page(
        ctx.collection, version, document_id=document_id, limit=limit, offset=offset
    )


@router.get("/{version}/chunks/stats", summary="Chunk count and size distribution")
async def chunk_stats(
    version: VersionNumber, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> ChunkStats:
    return await PipelineService(container, session).chunk_stats(ctx.collection, version)
