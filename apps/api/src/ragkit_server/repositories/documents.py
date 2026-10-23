from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, or_, select, update

from ragkit_server.models import Document, DocumentSection
from ragkit_server.models.enums import JobStatus, SourceType
from ragkit_server.repositories.base import Repository


class DocumentRepository(Repository):
    async def get(
        self, project_id: uuid.UUID, collection_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.collection_id == collection_id,
                Document.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, document_id: uuid.UUID) -> Document | None:
        """For the worker, which holds ids from a trusted job message."""
        result = await self.session.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def by_sha(self, collection_id: uuid.UUID, sha256: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.collection_id == collection_id,
                Document.sha256 == sha256,
                Document.source_type.in_([SourceType.FILE, SourceType.TEXT]),
            )
        )
        return result.scalar_one_or_none()

    async def by_url(self, collection_id: uuid.UUID, url: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.collection_id == collection_id,
                Document.source_type == SourceType.URL,
                Document.source_uri == url,
            )
        )
        return result.scalar_one_or_none()

    async def external_ids(self, collection_id: uuid.UUID, candidates: Sequence[str]) -> set[str]:
        """Which of these external ids already exist in the collection."""
        if not candidates:
            return set()
        result = await self.session.execute(
            select(Document.external_id).where(
                Document.collection_id == collection_id,
                Document.external_id.in_(list(candidates)),
            )
        )
        return set(result.scalars())

    async def external_id_map(
        self, collection_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        if not document_ids:
            return {}
        result = await self.session.execute(
            select(Document.id, Document.external_id).where(
                Document.collection_id == collection_id, Document.id.in_(list(document_ids))
            )
        )
        return {row.id: row.external_id for row in result.all()}

    async def add(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def page(
        self,
        collection_id: uuid.UUID,
        *,
        status: str | None,
        source_type: str | None,
        query: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        conditions: list[Any] = [Document.collection_id == collection_id]
        if status:
            conditions.append(Document.status == status)
        if source_type:
            conditions.append(Document.source_type == source_type)
        if query:
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    Document.title.ilike(pattern),
                    Document.external_id.ilike(pattern),
                    Document.source_uri.ilike(pattern),
                )
            )
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total

    async def ready_ids(self, collection_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self.session.execute(
            select(Document.id).where(
                Document.collection_id == collection_id, Document.status == JobStatus.READY
            )
        )
        return list(result.scalars())

    async def sections(self, document_id: uuid.UUID) -> list[DocumentSection]:
        result = await self.session.execute(
            select(DocumentSection)
            .where(DocumentSection.document_id == document_id)
            .order_by(DocumentSection.ordinal)
        )
        return list(result.scalars())

    async def replace_sections(
        self, document_id: uuid.UUID, rows: Sequence[dict[str, Any]]
    ) -> None:
        await self.session.execute(
            delete(DocumentSection).where(DocumentSection.document_id == document_id)
        )
        if rows:
            await self.session.execute(
                insert(DocumentSection), [{"document_id": document_id, **row} for row in rows]
            )

    async def unfinished_before(self, cutoff: datetime, limit: int = 100) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(
                Document.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
                Document.updated_at < cutoff,
            )
            .order_by(Document.updated_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def storage_keys_for_project(self, project_id: uuid.UUID) -> list[str]:
        result = await self.session.execute(
            select(Document.storage_key).where(
                Document.project_id == project_id, Document.storage_key.is_not(None)
            )
        )
        return [key for key in result.scalars() if key]

    async def storage_keys(self, collection_id: uuid.UUID) -> list[str]:
        result = await self.session.execute(
            select(Document.storage_key).where(
                Document.collection_id == collection_id, Document.storage_key.is_not(None)
            )
        )
        return [key for key in result.scalars() if key]

    async def mark(self, document_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(**values)
        )
