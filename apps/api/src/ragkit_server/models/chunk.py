from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Computed, ForeignKey, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from ragkit_server.db.base import Base, IdMixin
from ragkit_server.db.types import Embedding


class Chunk(IdMixin, Base):
    """A retrievable passage in one index, with both search representations."""

    __tablename__ = "chunks"

    index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("indexes.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    section_ordinal: Mapped[int]
    heading: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    # The sentence window around `text` (sentence_window strategy); what answerers and the
    # relevance judge read. Null means "same as text".
    context: Mapped[str | None] = mapped_column(Text)
    char_start: Mapped[int]
    char_end: Mapped[int]
    token_count: Mapped[int]
    # The document's metadata at indexing time, so filters touch one table.
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    # Untyped vector column: indexes with different embedding widths live in one table, and
    # each supported width has its own partial HNSW index (see the initial migration).
    embedding: Mapped[Any] = mapped_column(Embedding())
    embedding_dim: Mapped[int] = mapped_column(SmallInteger)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True),
    )
