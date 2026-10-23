"""Pipeline versions: create (reusing an index when the index settings match), activate,
describe with build progress, browse chunks, and preview a chunking configuration."""

from __future__ import annotations

import uuid
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.ai.embeddings import EmbeddingSpec, resolve_embedding
from ragkit_server.core.errors import NotFoundError, UnprocessableError
from ragkit_server.ingestion.chunkers import ChunkingOptions, chunk_sections
from ragkit_server.ingestion.cleaning import CleaningOptions, clean_sections
from ragkit_server.ingestion.parsers.registry import parse
from ragkit_server.ingestion.types import Block, ParsedSection, ParseError, ParseLimits
from ragkit_server.integrations.queue import Job
from ragkit_server.models import Collection, Index, PipelineVersion, Project
from ragkit_server.models.enums import DocumentKind, JobStatus, SectionKind
from ragkit_server.repositories.chunks import ChunkRepository
from ragkit_server.repositories.collections import CollectionRepository
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.repositories.pipelines import IndexProgress, PipelineRepository
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.pipeline import PipelineConfig, fingerprint, index_settings
from ragkit_server.schemas.pipelines import (
    ChunkOut,
    ChunkStats,
    IndexOut,
    PipelineVersionOut,
    PreviewOut,
    PreviewRequest,
)
from ragkit_server.services import audit
from ragkit_server.services.container import Container
from ragkit_server.services.principal import Principal

PREVIEW_LIMIT = 200


def sections_from_rows(rows: list[Any]) -> list[ParsedSection]:
    """Stored sections back into the shape the cleaning rules and chunkers read."""
    return [
        ParsedSection(
            SectionKind(row.kind),
            row.label,
            [Block(block["text"], heading_level=block.get("level")) for block in row.blocks],
        )
        for row in rows
    ]


def cleaning_options(config: PipelineConfig) -> CleaningOptions:
    return CleaningOptions(**config.cleaning.model_dump())


def chunking_options(config: PipelineConfig) -> ChunkingOptions:
    return ChunkingOptions(**config.chunking.model_dump())


class PipelineService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.pipelines = PipelineRepository(session)
        self.collections = CollectionRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)

    def resolve_spec(self, config: PipelineConfig) -> EmbeddingSpec:
        """The embedding model of a configuration, checked against this deployment."""
        embedding = config.embedding
        spec = resolve_embedding(
            embedding.model,
            None if embedding.provider == "registry" else embedding.provider,
            embedding.dim,
        )
        problem = self.c.embedders.availability(spec)
        if problem:
            raise UnprocessableError(problem, code="provider_unavailable")
        self.c.answerers.check(config.answer.answerer)
        return spec

    async def version(self, collection: Collection, number: int | None) -> PipelineVersion:
        if number is None:
            if collection.active_version_id is None:
                raise UnprocessableError(
                    "This collection has no active pipeline version.", code="no_active_version"
                )
            found = await self.pipelines.version_by_id(collection.active_version_id)
        else:
            found = await self.pipelines.version(collection.id, number)
        if found is None:
            raise NotFoundError(f"Pipeline version {number} not found.")
        return found

    async def create(
        self,
        project: Project,
        collection: Collection,
        principal: Principal,
        *,
        name: str,
        description: str,
        config: PipelineConfig,
        activate: bool,
    ) -> PipelineVersion:
        spec = self.resolve_spec(config)
        # The row lock serialises version numbering and index creation per collection.
        locked = await self.collections.get_for_update(collection.id)
        if locked is None:
            raise NotFoundError("Collection not found.")
        settings = index_settings(config, spec)
        settings_print = fingerprint(settings)
        index = await self.pipelines.index_by_fingerprint(collection.id, settings_print)
        created = index is None
        pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
        if index is None:
            index = await self.pipelines.add_index(
                Index(
                    project_id=project.id,
                    collection_id=collection.id,
                    fingerprint=settings_print,
                    config=settings,
                    embedding_model=spec.key,
                    embedding_dim=spec.dim,
                )
            )
            pairs = [(index.id, d) for d in await self.documents.ready_ids(collection.id)]
            await self.pipelines.ensure_entries(project.id, pairs)
        number = await self.pipelines.next_number(collection.id)
        version = await self.pipelines.add_version(
            PipelineVersion(
                project_id=project.id,
                collection_id=collection.id,
                version=number,
                name=name.strip(),
                description=description.strip(),
                config=config.model_dump(),
                index_id=index.id,
                created_by=principal.user_id,
            )
        )
        if activate or locked.active_version_id is None:
            locked.active_version_id = version.id
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="pipeline.created",
            target_type="pipeline_version",
            target_id=version.id,
            details={
                "collection": collection.slug,
                "version": number,
                "index": "new" if created else "shared",
            },
        )
        await self.session.commit()
        # After the commit, so the worker can read the rows it is told about. A lost message
        # is recovered by the reaper.
        for index_id, document_id in pairs:
            await self.c.queue.enqueue(Job.index(project.id, index_id, document_id))
        return version

    async def activate(
        self, project: Project, collection: Collection, principal: Principal, number: int
    ) -> PipelineVersion:
        version = await self.version(collection, number)
        collection.active_version_id = version.id
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="pipeline.activated",
            target_type="pipeline_version",
            target_id=version.id,
            details={"collection": collection.slug, "version": number},
        )
        await self.session.commit()
        return version

    async def describe(
        self, collection: Collection, versions: list[PipelineVersion]
    ) -> list[PipelineVersionOut]:
        index_ids = list({v.index_id for v in versions})
        indexes = await self.pipelines.indexes(index_ids)
        progress = await self.pipelines.progress(index_ids)
        sharing = await self.pipelines.versions_by_index(index_ids)
        return [
            PipelineVersionOut(
                id=v.id,
                version=v.version,
                name=v.name,
                description=v.description,
                config=v.config,
                active=v.id == collection.active_version_id,
                index=self._index_out(
                    indexes[v.index_id],
                    progress[v.index_id],
                    [n for n in sharing.get(v.index_id, []) if n != v.version],
                ),
                created_at=v.created_at,
            )
            for v in versions
        ]

    @staticmethod
    def _index_out(index: Index, progress: IndexProgress, shared_with: list[int]) -> IndexOut:
        return IndexOut.model_validate(
            {
                "id": index.id,
                "fingerprint": index.fingerprint,
                "embedding_model": index.embedding_model,
                "embedding_dim": index.embedding_dim,
                "status": progress.status.value,
                "progress": {
                    "total": progress.total,
                    "ready": progress.ready,
                    "processing": progress.processing,
                    "queued": progress.queued,
                    "failed": progress.failed,
                },
                "chunk_count": progress.chunks,
                "token_count": progress.tokens,
                "shared_with": shared_with,
            }
        )

    async def list(self, collection: Collection) -> list[PipelineVersionOut]:
        return await self.describe(collection, await self.pipelines.versions(collection.id))

    async def detail(self, collection: Collection, number: int) -> PipelineVersionOut:
        version = await self.version(collection, number)
        return (await self.describe(collection, [version]))[0]

    async def chunk_page(
        self,
        collection: Collection,
        number: int,
        *,
        document_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> Page[ChunkOut]:
        version = await self.version(collection, number)
        rows, total = await self.chunks.browse(
            version.index_id, document_id=document_id, limit=limit, offset=offset
        )
        return Page[ChunkOut](
            items=[
                ChunkOut(
                    id=r.id,
                    document_id=r.document_id,
                    document_title=r.document_title,
                    ordinal=r.ordinal,
                    heading=r.heading,
                    location=r.location,
                    text=r.text,
                    context=r.context,
                    token_count=r.token_count,
                )
                for r in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def chunk_stats(self, collection: Collection, number: int) -> ChunkStats:
        version = await self.version(collection, number)
        return ChunkStats.model_validate(await self.chunks.stats(version.index_id))

    async def preview(
        self, project: Project, collection: Collection, request: PreviewRequest
    ) -> PreviewOut:
        """Clean and chunk one document (or pasted text) with a candidate configuration."""
        if request.document_id is not None:
            document = await self.documents.get(project.id, collection.id, request.document_id)
            if document is None:
                raise NotFoundError("Document not found.")
            if document.status != JobStatus.READY:
                raise UnprocessableError("That document has not been parsed yet.")
            sections = sections_from_rows(await self.documents.sections(document.id))
        elif request.text:
            try:
                sections = parse(DocumentKind.MD, request.text.encode(), ParseLimits()).sections
            except ParseError as exc:
                raise UnprocessableError(str(exc)) from exc
        else:
            raise UnprocessableError("Give a document_id or some text to preview.")
        config = PipelineConfig(cleaning=request.cleaning, chunking=request.chunking)

        def run() -> tuple[list[Any], dict[str, Any]]:
            cleaned, report = clean_sections(sections, cleaning_options(config))
            drafts = chunk_sections(cleaned, self.c.tokens, chunking_options(config))
            return drafts, report.as_dict()

        drafts, report = await anyio.to_thread.run_sync(run)
        tokens = [d.token_count for d in drafts]
        edges = (0, 32, 64, 128, 256, 384, 512, 768, 1024)
        histogram = [
            {
                "from": low,
                "to": edges[i + 1] if i + 1 < len(edges) else -1,
                "count": sum(
                    1 for t in tokens if t >= low and (i + 1 == len(edges) or t < edges[i + 1])
                ),
            }
            for i, low in enumerate(edges)
        ]
        stats = ChunkStats(
            count=len(drafts),
            mean_tokens=round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
            min_tokens=min(tokens, default=0),
            max_tokens=max(tokens, default=0),
            histogram=histogram,
        )
        return PreviewOut(
            chunks=[
                {
                    "ordinal": d.ordinal,
                    "heading": d.heading,
                    "location": d.location,
                    "text": d.text,
                    "context": d.context,
                    "token_count": d.token_count,
                }
                for d in drafts[:PREVIEW_LIMIT]
            ],
            stats=stats,
            cleaning=report,
        )
