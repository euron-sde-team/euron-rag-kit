"""Chunks: written per (index, document), browsed per index, and the two candidate searches.

Vector search uses the HNSW index for the index's embedding width with iterative scans
(pgvector 0.8), so filtering by index, document and metadata does not starve the result
list the way post-filtering would. The width is a SQL literal taken from the supported set,
never a parameter: the planner must be able to match the partial index on every execution.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import (
    Float,
    String,
    bindparam,
    cast,
    delete,
    func,
    insert,
    literal_column,
    select,
    text,
    update,
)
from sqlalchemy.sql.elements import ColumnElement

from ragkit_server.db.types import SUPPORTED_DIMS, Embedding
from ragkit_server.ingestion.chunkers import ChunkDraft
from ragkit_server.models import Chunk, Document
from ragkit_server.repositories.base import Repository

_TUNE_HNSW = text(
    "SELECT set_config('hnsw.ef_search', :ef_search, true), "
    "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
)
_ENGLISH: ColumnElement[Any] = literal_column("'english'::regconfig")
HISTOGRAM_BUCKETS = (32, 64, 128, 256, 384, 512, 768, 1024)


@dataclass(frozen=True, slots=True)
class ChunkRow:
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    external_id: str
    ordinal: int
    section_ordinal: int
    heading: str
    location: str
    text: str
    context: str | None
    token_count: int
    metadata: dict[str, Any]


def _scope(
    index_id: uuid.UUID,
    filters: ColumnElement[bool] | None,
    document_ids: Sequence[uuid.UUID] | None,
) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [Chunk.index_id == index_id]
    if filters is not None:
        conditions.append(filters)
    if document_ids:
        conditions.append(Chunk.document_id.in_(list(document_ids)))
    return conditions


class ChunkRepository(Repository):
    async def replace_for_document(
        self,
        *,
        index_id: uuid.UUID,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        drafts: Sequence[ChunkDraft],
        embeddings: np.ndarray,
        dim: int,
        metadata: dict[str, Any],
    ) -> None:
        """Swap a document's chunks in one index, in the caller's transaction."""
        await self.session.execute(
            delete(Chunk).where(Chunk.index_id == index_id, Chunk.document_id == document_id)
        )
        if drafts:
            await self.session.execute(
                insert(Chunk),
                [
                    {
                        "index_id": index_id,
                        "collection_id": collection_id,
                        "document_id": document_id,
                        "ordinal": d.ordinal,
                        "section_ordinal": d.section_ordinal,
                        "heading": d.heading,
                        "location": d.location[:300],
                        "text": d.text,
                        "context": d.context,
                        "char_start": d.char_start,
                        "char_end": d.char_end,
                        "token_count": d.token_count,
                        "meta": metadata,
                        "embedding": embeddings[i],
                        "embedding_dim": dim,
                    }
                    for i, d in enumerate(drafts)
                ],
            )

    async def set_metadata(self, document_id: uuid.UUID, metadata: dict[str, Any]) -> None:
        await self.session.execute(
            update(Chunk).where(Chunk.document_id == document_id).values(meta=metadata)
        )

    async def browse(
        self,
        index_id: uuid.UUID,
        *,
        document_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ChunkRow], int]:
        conditions: list[ColumnElement[bool]] = [Chunk.index_id == index_id]
        if document_id is not None:
            conditions.append(Chunk.document_id == document_id)
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            self._rows()
            .where(*conditions)
            .order_by(Document.title, Chunk.document_id, Chunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
        return [_row(r) for r in result.all()], total

    async def stats(self, index_id: uuid.UUID) -> dict[str, Any]:
        summary = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.avg(Chunk.token_count), 0),
                    func.coalesce(func.min(Chunk.token_count), 0),
                    func.coalesce(func.max(Chunk.token_count), 0),
                ).where(Chunk.index_id == index_id)
            )
        ).one()
        bucket = func.width_bucket(
            Chunk.token_count, literal_column(f"ARRAY{list(HISTOGRAM_BUCKETS)}")
        )
        rows = (
            await self.session.execute(
                select(bucket.label("bucket"), func.count().label("chunks"))
                .where(Chunk.index_id == index_id)
                .group_by("bucket")
            )
        ).all()
        counts = {int(row.bucket): int(row.chunks) for row in rows}
        edges = (0, *HISTOGRAM_BUCKETS)
        histogram = [
            {
                "from": edges[i],
                "to": edges[i + 1] if i + 1 < len(edges) else -1,
                "count": counts.get(i, 0),
            }
            for i in range(len(edges))
        ]
        return {
            "count": int(summary[0]),
            "mean_tokens": round(float(summary[1]), 1),
            "min_tokens": int(summary[2]),
            "max_tokens": int(summary[3]),
            "histogram": histogram,
        }

    # Candidate searches -----------------------------------------------------------------

    async def vector_candidates(
        self,
        *,
        index_id: uuid.UUID,
        dim: int,
        query: np.ndarray,
        filters: ColumnElement[bool] | None,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        if dim not in SUPPORTED_DIMS:
            raise ValueError(f"unsupported embedding width {dim}")
        await self.session.execute(_TUNE_HNSW, {"ef_search": str(max(40, limit * 2))})
        typed = cast(Chunk.embedding, Embedding(dim))
        distance = typed.op("<=>", return_type=Float)(
            bindparam("query_vector", value=query, type_=Embedding())
        )
        rows = (
            await self.session.execute(
                select(Chunk.id, (1 - distance).label("score"))
                .where(
                    *_scope(index_id, filters, document_ids),
                    Chunk.embedding_dim == literal_column(str(dim)),
                )
                .order_by(distance)
                .limit(limit)
            )
        ).all()
        # relaxed_order may return near-ties out of order; fusion needs the true order.
        return sorted(((r.id, float(r.score)) for r in rows), key=lambda item: -item[1])

    async def keyword_candidates(
        self,
        *,
        index_id: uuid.UUID,
        tsquery: str,
        filters: ColumnElement[bool] | None,
        document_ids: Sequence[uuid.UUID] | None,
        limit: int,
    ) -> list[tuple[uuid.UUID, float]]:
        query = func.to_tsquery(_ENGLISH, bindparam("tsquery", value=tsquery, type_=String))
        rank = func.ts_rank_cd(Chunk.tsv, query, 32)
        rows = (
            await self.session.execute(
                select(Chunk.id, rank.label("rank"))
                .where(*_scope(index_id, filters, document_ids), Chunk.tsv.op("@@")(query))
                .order_by(rank.desc(), Chunk.id)
                .limit(limit)
            )
        ).all()
        return [(r.id, float(r.rank)) for r in rows]

    async def hydrate(
        self, index_id: uuid.UUID, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ChunkRow]:
        if not ids:
            return {}
        result = await self.session.execute(
            self._rows().where(Chunk.index_id == index_id, Chunk.id.in_(list(ids)))
        )
        return {row.id: _row(row) for row in result.all()}

    @staticmethod
    def _rows() -> Any:
        return select(
            Chunk.id,
            Chunk.document_id,
            Document.title.label("document_title"),
            Document.external_id,
            Chunk.ordinal,
            Chunk.section_ordinal,
            Chunk.heading,
            Chunk.location,
            Chunk.text,
            Chunk.context,
            Chunk.token_count,
            Chunk.meta.label("metadata"),
        ).join(Document, Document.id == Chunk.document_id)


def _row(row: Any) -> ChunkRow:
    return ChunkRow(
        id=row.id,
        document_id=row.document_id,
        document_title=row.document_title,
        external_id=row.external_id,
        ordinal=row.ordinal,
        section_ordinal=row.section_ordinal,
        heading=row.heading,
        location=row.location,
        text=row.text,
        context=row.context,
        token_count=row.token_count,
        metadata=row.metadata or {},
    )
