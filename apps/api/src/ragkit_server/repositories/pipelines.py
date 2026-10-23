from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ragkit_server.models import Index, IndexEntry, PipelineVersion
from ragkit_server.models.enums import IndexStatus, JobStatus
from ragkit_server.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class IndexProgress:
    total: int = 0
    ready: int = 0
    processing: int = 0
    queued: int = 0
    failed: int = 0
    chunks: int = 0
    tokens: int = 0

    @property
    def status(self) -> IndexStatus:
        if self.total == 0:
            return IndexStatus.EMPTY
        if self.queued or self.processing:
            return IndexStatus.BUILDING
        if self.failed == self.total:
            return IndexStatus.FAILED
        return IndexStatus.READY


class PipelineRepository(Repository):
    # Versions ---------------------------------------------------------------------------

    async def versions(self, collection_id: uuid.UUID) -> list[PipelineVersion]:
        result = await self.session.execute(
            select(PipelineVersion)
            .where(PipelineVersion.collection_id == collection_id)
            .order_by(PipelineVersion.version.desc())
        )
        return list(result.scalars())

    async def version(self, collection_id: uuid.UUID, number: int) -> PipelineVersion | None:
        result = await self.session.execute(
            select(PipelineVersion).where(
                PipelineVersion.collection_id == collection_id, PipelineVersion.version == number
            )
        )
        return result.scalar_one_or_none()

    async def version_by_id(self, version_id: uuid.UUID) -> PipelineVersion | None:
        return await self.session.get(PipelineVersion, version_id)

    async def versions_by_ids(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, PipelineVersion]:
        if not ids:
            return {}
        result = await self.session.execute(
            select(PipelineVersion).where(PipelineVersion.id.in_(list(ids)))
        )
        return {v.id: v for v in result.scalars()}

    async def next_number(self, collection_id: uuid.UUID) -> int:
        """Callers hold the collection row lock, so two creates cannot take the same number."""
        current = await self.session.scalar(
            select(func.max(PipelineVersion.version)).where(
                PipelineVersion.collection_id == collection_id
            )
        )
        return int(current or 0) + 1

    async def add_version(self, version: PipelineVersion) -> PipelineVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def versions_by_index(self, index_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[int]]:
        if not index_ids:
            return {}
        result = await self.session.execute(
            select(PipelineVersion.index_id, PipelineVersion.version)
            .where(PipelineVersion.index_id.in_(list(index_ids)))
            .order_by(PipelineVersion.version)
        )
        grouped: dict[uuid.UUID, list[int]] = {}
        for row in result.all():
            grouped.setdefault(row.index_id, []).append(int(row.version))
        return grouped

    # Indexes ----------------------------------------------------------------------------

    async def index(self, index_id: uuid.UUID) -> Index | None:
        return await self.session.get(Index, index_id)

    async def indexes(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Index]:
        if not ids:
            return {}
        result = await self.session.execute(select(Index).where(Index.id.in_(list(ids))))
        return {index.id: index for index in result.scalars()}

    async def index_by_fingerprint(
        self, collection_id: uuid.UUID, fingerprint: str
    ) -> Index | None:
        result = await self.session.execute(
            select(Index).where(
                Index.collection_id == collection_id, Index.fingerprint == fingerprint
            )
        )
        return result.scalar_one_or_none()

    async def collection_index_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(Index.id).where(Index.collection_id == collection_id)
        )
        return list(result.scalars())

    async def add_index(self, index: Index) -> Index:
        self.session.add(index)
        await self.session.flush()
        return index

    # Entries ----------------------------------------------------------------------------

    async def ensure_entries(
        self, project_id: uuid.UUID, pairs: Sequence[tuple[uuid.UUID, uuid.UUID]]
    ) -> None:
        """Queue (index, document) pairs; existing entries are left as they are."""
        if not pairs:
            return
        await self.session.execute(
            pg_insert(IndexEntry)
            .values(
                [
                    {
                        "index_id": index_id,
                        "document_id": document_id,
                        "project_id": project_id,
                        "status": JobStatus.QUEUED,
                    }
                    for index_id, document_id in pairs
                ]
            )
            .on_conflict_do_nothing(index_elements=["index_id", "document_id"])
        )

    async def requeue_document(self, document_id: uuid.UUID) -> list[uuid.UUID]:
        """Put every entry of a re-parsed document back in the queue; returns the index ids."""
        result = await self.session.execute(
            update(IndexEntry)
            .where(IndexEntry.document_id == document_id)
            .values(status=JobStatus.QUEUED, attempts=0, error=None)
            .returning(IndexEntry.index_id)
        )
        return list(result.scalars())

    async def entry_for_update(
        self, index_id: uuid.UUID, document_id: uuid.UUID
    ) -> IndexEntry | None:
        result = await self.session.execute(
            select(IndexEntry)
            .where(IndexEntry.index_id == index_id, IndexEntry.document_id == document_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def mark_entry(self, index_id: uuid.UUID, document_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(
            update(IndexEntry)
            .where(IndexEntry.index_id == index_id, IndexEntry.document_id == document_id)
            .values(**values)
        )

    async def entries_for_document(self, document_id: uuid.UUID) -> list[IndexEntry]:
        result = await self.session.execute(
            select(IndexEntry).where(IndexEntry.document_id == document_id)
        )
        return list(result.scalars())

    async def progress(self, index_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, IndexProgress]:
        if not index_ids:
            return {}
        result = await self.session.execute(
            select(
                IndexEntry.index_id,
                func.count().label("total"),
                func.count().filter(IndexEntry.status == JobStatus.READY).label("ready"),
                func.count().filter(IndexEntry.status == JobStatus.PROCESSING).label("processing"),
                func.count().filter(IndexEntry.status == JobStatus.QUEUED).label("queued"),
                func.count().filter(IndexEntry.status == JobStatus.FAILED).label("failed"),
                func.coalesce(func.sum(IndexEntry.chunk_count), 0).label("chunks"),
                func.coalesce(func.sum(IndexEntry.token_count), 0).label("tokens"),
            )
            .where(IndexEntry.index_id.in_(list(index_ids)))
            .group_by(IndexEntry.index_id)
        )
        progress = {
            row.index_id: IndexProgress(
                total=int(row.total),
                ready=int(row.ready),
                processing=int(row.processing),
                queued=int(row.queued),
                failed=int(row.failed),
                chunks=int(row.chunks),
                tokens=int(row.tokens),
            )
            for row in result.all()
        }
        return {index_id: progress.get(index_id, IndexProgress()) for index_id in index_ids}

    async def unfinished_entries_before(
        self, cutoff: datetime, limit: int = 200
    ) -> list[IndexEntry]:
        result = await self.session.execute(
            select(IndexEntry)
            .where(
                IndexEntry.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
                IndexEntry.updated_at < cutoff,
            )
            .order_by(IndexEntry.updated_at)
            .limit(limit)
        )
        return list(result.scalars())
