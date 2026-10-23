"""Ingestion and the document library of a collection."""

from __future__ import annotations

import uuid
from typing import Annotated, Any
from urllib.parse import quote

import orjson
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from ragkit_server.api.deps import (
    CollectionEditorDep,
    CollectionViewerDep,
    ContainerDep,
    SessionDep,
    rate_limit,
)
from ragkit_server.core.errors import UnprocessableError
from ragkit_server.models import Document
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.documents import (
    DocumentDetail,
    DocumentImport,
    DocumentOut,
    DocumentUpdate,
    IngestResult,
    RejectedSource,
    SectionOut,
)
from ragkit_server.services.documents import DocumentService, IncomingFile, IntakeOutcome

router = APIRouter(
    prefix="/api/v1/projects/{project}/collections/{collection}/documents", tags=["documents"]
)
MAX_FILES_PER_REQUEST = 20
_INGEST_LIMIT = [Depends(rate_limit("ingest", "rate_limit_ingest"))]


def _result(outcome: IntakeOutcome) -> IngestResult:
    return IngestResult(
        created=[DocumentOut.model_validate(d) for d in outcome.created],
        duplicates=[DocumentOut.model_validate(d) for d in outcome.duplicates],
        rejected=[RejectedSource(name=n, code=c, message=m) for n, c, m in outcome.rejected],
    )


@router.get("", summary="The documents of a collection")
async def list_documents(
    ctx: CollectionViewerDep,
    container: ContainerDep,
    session: SessionDep,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(queued|processing|ready|failed)$")
    ] = None,
    source: Annotated[str | None, Query(pattern="^(file|url|text)$")] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[DocumentOut]:
    items, total = await DocumentService(container, session).page(
        ctx.collection,
        status=status_filter,
        source_type=source,
        query=q,
        limit=limit,
        offset=offset,
    )
    return Page[DocumentOut](
        items=[DocumentOut.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    summary="Upload files (PDF, Word, Markdown, HTML, text, CSV)",
    status_code=status.HTTP_201_CREATED,
    dependencies=_INGEST_LIMIT,
)
async def upload_documents(
    ctx: CollectionEditorDep,
    container: ContainerDep,
    session: SessionDep,
    files: Annotated[list[UploadFile], File(description="Up to 20 files per request.")],
    metadata: Annotated[
        str | None, Form(description="JSON object applied to every file, for filters.")
    ] = None,
) -> IngestResult:
    if len(files) > MAX_FILES_PER_REQUEST:
        raise UnprocessableError(f"Upload at most {MAX_FILES_PER_REQUEST} files at a time.")
    parsed: dict[str, Any] = {}
    if metadata:
        try:
            parsed = orjson.loads(metadata)
        except orjson.JSONDecodeError as exc:
            raise UnprocessableError("metadata must be a JSON object.") from exc
        if not isinstance(parsed, dict):
            raise UnprocessableError("metadata must be a JSON object.")
    limit = container.settings.max_upload_bytes
    incoming = []
    for upload in files:
        # Read one byte past the limit: enough to know the file is too large, never more.
        data = await upload.read(limit + 1)
        incoming.append(IncomingFile(filename=upload.filename or "upload", data=data))
        await upload.close()
    outcome = await DocumentService(container, session).upload(
        ctx.project, ctx.collection, ctx.principal, incoming, parsed
    )
    return _result(outcome)


@router.post(
    "/import",
    summary="Add text and URL sources (JSON, up to 100 per request)",
    status_code=status.HTTP_201_CREATED,
    dependencies=_INGEST_LIMIT,
)
async def import_documents(
    body: DocumentImport, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> IngestResult:
    outcome = await DocumentService(container, session).import_sources(
        ctx.project, ctx.collection, ctx.principal, body.items
    )
    return _result(outcome)


async def _document(
    document_id: uuid.UUID, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> Document:
    return await DocumentService(container, session).get(ctx.project, ctx.collection, document_id)


DocumentDep = Annotated[Document, Depends(_document)]


@router.get("/{document_id}", summary="A document with its sections and index status")
async def get_document(
    document: DocumentDep, container: ContainerDep, session: SessionDep
) -> DocumentDetail:
    service = DocumentService(container, session)
    sections = await service.sections(document)
    return DocumentDetail.model_validate(
        {
            **DocumentOut.model_validate(document).model_dump(),
            "sections": [SectionOut.model_validate(s) for s in sections],
            "indexes": await service.index_entries(document),
        }
    )


@router.get(
    "/{document_id}/file", summary="Download the original", response_class=StreamingResponse
)
async def download_document(
    document: DocumentDep, container: ContainerDep, session: SessionDep
) -> StreamingResponse:
    filename = document.source_uri if document.source_type == "file" else document.external_id
    disposition = f"attachment; filename*=UTF-8''{quote(filename or 'original')}"
    return StreamingResponse(
        DocumentService(container, session).download(document),
        media_type=document.mime_type or "application/octet-stream",
        headers={"content-disposition": disposition},
    )


@router.patch("/{document_id}", summary="Change a document's title or metadata")
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    ctx: CollectionEditorDep,
    container: ContainerDep,
    session: SessionDep,
) -> DocumentOut:
    service = DocumentService(container, session)
    document = await service.get(ctx.project, ctx.collection, document_id)
    updated = await service.update(
        ctx.project,
        ctx.collection,
        ctx.principal,
        document,
        title=body.title,
        metadata=body.metadata,
    )
    return DocumentOut.model_validate(updated)


@router.post("/{document_id}/reprocess", summary="Parse and index the document again")
async def reprocess_document(
    document_id: uuid.UUID, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> DocumentOut:
    service = DocumentService(container, session)
    document = await service.get(ctx.project, ctx.collection, document_id)
    return DocumentOut.model_validate(await service.reprocess(ctx.project, ctx.principal, document))


@router.delete("/{document_id}", summary="Delete a document and its chunks", status_code=204)
async def delete_document(
    document_id: uuid.UUID, ctx: CollectionEditorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = DocumentService(container, session)
    document = await service.get(ctx.project, ctx.collection, document_id)
    await service.delete(ctx.project, ctx.collection, ctx.principal, document)
