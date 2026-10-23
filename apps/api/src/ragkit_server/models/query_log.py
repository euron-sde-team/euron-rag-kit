from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ragkit_server.db.base import Base, IdMixin


class QueryLog(IdMixin, Base):
    """One served query or answer, for the analytics view (evaluation traffic is not logged)."""

    __tablename__ = "query_logs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    pipeline_version: Mapped[int]
    kind: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(8))
    rerank: Mapped[str] = mapped_column(String(16))
    top_k: Mapped[int]
    hit_count: Mapped[int]
    top_score: Mapped[float | None]
    latency_ms: Mapped[int]
    cached: Mapped[bool] = mapped_column(default=False)
    answerer: Mapped[str | None] = mapped_column(String(32))
    query_hash: Mapped[str] = mapped_column(String(64))
    query_text: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
