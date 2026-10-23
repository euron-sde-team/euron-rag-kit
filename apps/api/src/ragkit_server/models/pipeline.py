from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ragkit_server.db.base import Base, IdMixin


class Index(IdMixin, Base):
    """Index settings (cleaning, chunking, embedding) materialised over a collection.

    Identified by the fingerprint of those settings: pipeline versions that differ only in
    retrieval or answering share one index and need no rebuild.
    """

    __tablename__ = "indexes"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dim: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IndexEntry(Base):
    """One document in one index: the unit of indexing work and its outcome."""

    __tablename__ = "index_entries"

    index_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("indexes.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16))
    chunk_count: Mapped[int] = mapped_column(default=0)
    token_count: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PipelineVersion(IdMixin, Base):
    """An immutable, numbered pipeline configuration. Changing anything is a new version."""

    __tablename__ = "pipeline_versions"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    version: Mapped[int]
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("indexes.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
