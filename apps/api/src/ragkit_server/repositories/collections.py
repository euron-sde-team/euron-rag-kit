from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update

from ragkit_server.models import Collection, Document, IndexEntry, PipelineVersion
from ragkit_server.models.enums import JobStatus
from ragkit_server.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class CollectionStats:
    collection: Collection
    active_version: int | None
    version_count: int
    document_count: int
    ready_documents: int
    chunk_count: int


class CollectionRepository(Repository):
    async def get(self, project_id: uuid.UUID, ref: str) -> Collection | None:
        """By id or slug, always within the project."""
        condition = Collection.slug == ref.lower()
        with contextlib.suppress(ValueError):
            condition = Collection.id == uuid.UUID(ref)
        result = await self.session.execute(
            select(Collection).where(Collection.project_id == project_id, condition)
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, collection_id: uuid.UUID) -> Collection | None:
        result = await self.session.execute(
            select(Collection).where(Collection.id == collection_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def slug_taken(self, project_id: uuid.UUID, slug: str) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count()).where(
                    Collection.project_id == project_id, Collection.slug == slug
                )
            )
        )

    async def add(self, collection: Collection) -> Collection:
        self.session.add(collection)
        await self.session.flush()
        return collection

    async def with_stats(
        self, project_id: uuid.UUID, collection_ids: list[uuid.UUID] | None = None
    ) -> list[CollectionStats]:
        """Every collection of a project with its counts, in four grouped queries (no N+1)."""
        query = select(Collection).where(Collection.project_id == project_id)
        if collection_ids is not None:
            query = query.where(Collection.id.in_(collection_ids))
        collections = list((await self.session.execute(query.order_by(Collection.name))).scalars())
        if not collections:
            return []
        ids = [c.id for c in collections]
        version_counts: dict[uuid.UUID, int] = {
            row.collection_id: int(row.versions)
            for row in (
                await self.session.execute(
                    select(PipelineVersion.collection_id, func.count().label("versions"))
                    .where(PipelineVersion.collection_id.in_(ids))
                    .group_by(PipelineVersion.collection_id)
                )
            ).all()
        }
        active_ids = [c.active_version_id for c in collections if c.active_version_id]
        active = {
            row.collection_id: (int(row.version), row.index_id)
            for row in (
                await self.session.execute(
                    select(
                        PipelineVersion.collection_id,
                        PipelineVersion.version,
                        PipelineVersion.index_id,
                    ).where(PipelineVersion.id.in_(active_ids))
                )
            ).all()
        }
        documents = {
            row.collection_id: (int(row.total), int(row.ready))
            for row in (
                await self.session.execute(
                    select(
                        Document.collection_id,
                        func.count().label("total"),
                        func.count().filter(Document.status == JobStatus.READY).label("ready"),
                    )
                    .where(Document.collection_id.in_(ids))
                    .group_by(Document.collection_id)
                )
            ).all()
        }
        chunks: dict[uuid.UUID, int] = {
            row.index_id: int(row.chunks or 0)
            for row in (
                await self.session.execute(
                    select(IndexEntry.index_id, func.sum(IndexEntry.chunk_count).label("chunks"))
                    .where(IndexEntry.index_id.in_([index for _, index in active.values()]))
                    .group_by(IndexEntry.index_id)
                )
            ).all()
        }
        stats = []
        for c in collections:
            version, index_id = active.get(c.id, (None, None))
            total, ready = documents.get(c.id, (0, 0))
            stats.append(
                CollectionStats(
                    collection=c,
                    active_version=version,
                    version_count=version_counts.get(c.id, 0),
                    document_count=total,
                    ready_documents=ready,
                    chunk_count=chunks.get(index_id, 0) if index_id else 0,
                )
            )
        return stats

    async def bump_corpus_version(self, collection_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Collection)
            .where(Collection.id == collection_id)
            .values(corpus_version=Collection.corpus_version + 1)
        )
