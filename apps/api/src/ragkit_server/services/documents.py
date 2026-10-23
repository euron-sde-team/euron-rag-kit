"""Ingestion intake: files, text and URLs into a collection; the document library."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any
from urllib.parse import urlsplit

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.core.errors import AppError, ConflictError, NotFoundError, UnprocessableError
from ragkit_server.core.ids import uuid7
from ragkit_server.core.logging import get_logger
from ragkit_server.ingestion.sniff import (
    MIME_TYPES,
    detect_kind,
    external_id_for,
    slugify,
    title_from_filename,
)
from ragkit_server.integrations.fetcher import check_url_shape
from ragkit_server.integrations.queue import Job
from ragkit_server.integrations.storage import document_key
from ragkit_server.models import Collection, Document, DocumentSection, Project
from ragkit_server.models.enums import DocumentKind, JobStatus, SourceType
from ragkit_server.repositories.chunks import ChunkRepository
from ragkit_server.repositories.collections import CollectionRepository
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.repositories.pipelines import PipelineRepository
from ragkit_server.schemas.documents import IndexEntryOut, TextSource, UrlSource
from ragkit_server.services import audit
from ragkit_server.services.container import Container
from ragkit_server.services.principal import Principal

log = get_logger("ragkit.documents")
_METADATA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
MAX_METADATA_BYTES = 8 * 1024


@dataclass(frozen=True, slots=True)
class IncomingFile:
    filename: str
    data: bytes


@dataclass(slots=True)
class IntakeOutcome:
    created: list[Document] = field(default_factory=list)
    duplicates: list[Document] = field(default_factory=list)
    rejected: list[tuple[str, str, str]] = field(default_factory=list)


def clean_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip() or "upload"
    return "".join(ch for ch in base if ch.isprintable())[:300]


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Top-level keys must be filterable names; the whole object stays small."""
    bad = [key for key in metadata if not _METADATA_KEY.match(key)]
    if bad:
        raise UnprocessableError(
            f"Metadata key '{bad[0]}' is not valid: use letters, digits, _ and -.",
            code="invalid_metadata",
        )
    if len(orjson.dumps(metadata)) > MAX_METADATA_BYTES:
        raise UnprocessableError("Metadata is limited to 8 KB.", code="invalid_metadata")
    return metadata


def url_external_id(url: str) -> str:
    parts = urlsplit(url)
    return slugify(f"{parts.hostname or ''}{parts.path}", fallback="page")


class DocumentService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.documents = DocumentRepository(session)
        self.pipelines = PipelineRepository(session)

    async def get(
        self, project: Project, collection: Collection, document_id: uuid.UUID
    ) -> Document:
        document = await self.documents.get(project.id, collection.id, document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return document

    async def page(
        self,
        collection: Collection,
        *,
        status: str | None,
        source_type: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        return await self.documents.page(
            collection.id,
            status=status,
            source_type=source_type,
            query=query,
            limit=limit,
            offset=offset,
        )

    async def sections(self, document: Document) -> list[DocumentSection]:
        return await self.documents.sections(document.id)

    async def index_entries(self, document: Document) -> list[IndexEntryOut]:
        entries = await self.pipelines.entries_for_document(document.id)
        versions = await self.pipelines.versions_by_index([e.index_id for e in entries])
        return [
            IndexEntryOut(
                pipeline_versions=versions.get(entry.index_id, []),
                index_id=entry.index_id,
                status=entry.status,
                chunk_count=entry.chunk_count,
                error=entry.error,
            )
            for entry in sorted(entries, key=lambda e: versions.get(e.index_id, [0])[0])
        ]

    async def _unique_external_id(
        self, collection: Collection, wanted: str, taken: set[str]
    ) -> str:
        candidate = wanted
        suffix = 2
        while candidate in taken or await self.documents.external_ids(collection.id, [candidate]):
            candidate = f"{wanted}-{suffix}"
            suffix += 1
        taken.add(candidate)
        return candidate

    async def upload(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        files: Sequence[IncomingFile],
        metadata: dict[str, Any],
    ) -> IntakeOutcome:
        validate_metadata(metadata)
        outcome = IntakeOutcome()
        limit = self.c.settings.max_upload_bytes
        taken: set[str] = set()
        jobs: list[Job] = []
        for incoming in files:
            filename = clean_filename(incoming.filename)
            try:
                if not incoming.data:
                    raise AppError("The file is empty.", code="empty_file")
                if len(incoming.data) > limit:
                    raise AppError(
                        f"The file is larger than {self.c.settings.max_upload_mb} MB.",
                        code="payload_too_large",
                    )
                kind = detect_kind(filename, incoming.data[:8192])
            except AppError as exc:
                outcome.rejected.append((filename, exc.code, exc.message))
                continue
            sha256 = hashlib.sha256(incoming.data).hexdigest()
            existing = await self.documents.by_sha(collection.id, sha256)
            if existing is not None:
                outcome.duplicates.append(existing)
                continue
            document = await self._store(
                project,
                collection,
                principal,
                data=incoming.data,
                kind=kind,
                title=title_from_filename(filename),
                external_id=await self._unique_external_id(
                    collection, external_id_for(filename), taken
                ),
                source_type=SourceType.FILE,
                source_uri=filename,
                metadata=metadata,
                sha256=sha256,
                extension=PurePath(filename).suffix.lower(),
            )
            outcome.created.append(document)
            jobs.append(Job.parse(project.id, document.id))
        await self.session.commit()
        for job in jobs:
            await self.c.queue.enqueue(job)
        return outcome

    async def import_sources(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        items: Sequence[TextSource | UrlSource],
    ) -> IntakeOutcome:
        outcome = IntakeOutcome()
        taken: set[str] = set()
        jobs: list[Job] = []
        requested = [item.external_id for item in items if item.external_id]
        if len(requested) != len(set(requested)):
            raise UnprocessableError("Two sources in this request share an external_id.")
        clashing = await self.documents.external_ids(collection.id, requested)
        for item in items:
            name = item.title if isinstance(item, TextSource) else str(item.url)
            if item.external_id and item.external_id in clashing:
                outcome.rejected.append(
                    (name, "duplicate_external_id", f"'{item.external_id}' is already used.")
                )
                continue
            validate_metadata(item.metadata)
            if isinstance(item, TextSource):
                document, created = await self._import_text(
                    project, collection, principal, item, taken
                )
            else:
                document, created = await self._import_url(
                    project, collection, principal, item, taken
                )
            if created:
                outcome.created.append(document)
                jobs.append(Job.parse(project.id, document.id))
            else:
                outcome.duplicates.append(document)
        await self.session.commit()
        for job in jobs:
            await self.c.queue.enqueue(job)
        return outcome

    async def _import_text(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        item: TextSource,
        taken: set[str],
    ) -> tuple[Document, bool]:
        data = item.text.encode()
        sha256 = hashlib.sha256(data).hexdigest()
        existing = await self.documents.by_sha(collection.id, sha256)
        if existing is not None:
            return existing, False
        kind = DocumentKind.MD if item.format == "markdown" else DocumentKind.TXT
        external_id = item.external_id or await self._unique_external_id(
            collection, slugify(item.title), taken
        )
        document = await self._store(
            project,
            collection,
            principal,
            data=data,
            kind=kind,
            title=item.title.strip(),
            external_id=external_id,
            source_type=SourceType.TEXT,
            source_uri=None,
            metadata=item.metadata,
            sha256=sha256,
            extension=".md" if kind is DocumentKind.MD else ".txt",
        )
        return document, True

    async def _import_url(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        item: UrlSource,
        taken: set[str],
    ) -> tuple[Document, bool]:
        url = str(item.url)
        check_url_shape(url)
        existing = await self.documents.by_url(collection.id, url)
        if existing is not None:
            return existing, False
        external_id = item.external_id or await self._unique_external_id(
            collection, url_external_id(url), taken
        )
        document = await self.documents.add(
            Document(
                id=uuid7(),
                project_id=project.id,
                collection_id=collection.id,
                external_id=external_id,
                title=(item.title or url)[:300],
                source_type=SourceType.URL,
                source_uri=url,
                meta=item.metadata,
                status=JobStatus.QUEUED,
                created_by=principal.user_id,
            )
        )
        await self._audit_added(project, principal, document)
        return document, True

    async def _store(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        *,
        data: bytes,
        kind: DocumentKind,
        title: str,
        external_id: str,
        source_type: SourceType,
        source_uri: str | None,
        metadata: dict[str, Any],
        sha256: str,
        extension: str,
    ) -> Document:
        document_id = uuid7()
        key = document_key(project.id, collection.id, document_id, extension)
        await self.c.storage.put(key, data, MIME_TYPES[kind])
        document = await self.documents.add(
            Document(
                id=document_id,
                project_id=project.id,
                collection_id=collection.id,
                external_id=external_id,
                title=title[:300],
                source_type=source_type,
                source_uri=source_uri,
                kind=kind.value,
                mime_type=MIME_TYPES[kind],
                size_bytes=len(data),
                sha256=sha256,
                storage_key=key,
                meta=metadata,
                status=JobStatus.QUEUED,
                created_by=principal.user_id,
            )
        )
        await self._audit_added(project, principal, document)
        return document

    async def _audit_added(
        self, project: Project, principal: Principal, document: Document
    ) -> None:
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="document.added",
            target_type="document",
            target_id=document.id,
            details={"source": document.source_type, "external_id": document.external_id},
        )

    async def update(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        document: Document,
        *,
        title: str | None,
        metadata: dict[str, Any] | None,
    ) -> Document:
        if title is not None:
            document.title = title.strip()
        if metadata is not None:
            document.meta = validate_metadata(metadata)
            # Chunks carry a copy of the metadata for filtering; keep it current without a
            # rebuild, and retire cached results that a filter may now answer differently.
            await ChunkRepository(self.session).set_metadata(document.id, metadata)
            await CollectionRepository(self.session).bump_corpus_version(collection.id)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="document.updated",
            target_type="document",
            target_id=document.id,
            details={"title": title is not None, "metadata": metadata is not None},
        )
        await self.session.commit()
        return document

    def download(self, document: Document) -> AsyncIterator[bytes]:
        if not document.storage_key:
            raise NotFoundError("This source has no stored original yet.")
        return self.c.storage.stream(document.storage_key)

    async def delete(
        self, project: Project, collection: Collection, principal: Principal, document: Document
    ) -> None:
        key = document.storage_key
        await self.session.delete(document)
        await CollectionRepository(self.session).bump_corpus_version(collection.id)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="document.deleted",
            target_type="document",
            target_id=document.id,
            details={"external_id": document.external_id},
        )
        await self.session.commit()
        if key:
            try:
                await self.c.storage.delete(key)
            except Exception:
                log.warning("storage_delete_failed", key=key)

    async def reprocess(
        self, project: Project, principal: Principal, document: Document
    ) -> Document:
        if document.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
            raise ConflictError("This document is already being processed.")
        document.status = JobStatus.QUEUED
        document.error = None
        document.attempts = 0
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="document.reprocessed",
            target_type="document",
            target_id=document.id,
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job.parse(project.id, document.id))
        return document
