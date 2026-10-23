from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ragkit_server.db.base import Base, IdMixin, TimestampMixin


class Collection(IdMixin, TimestampMixin, Base):
    """A corpus with its own documents, pipeline versions and datasets."""

    __tablename__ = "collections"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    # The version queries use when they do not name one. Versions reference collections too,
    # so this side of the cycle is added after both tables exist (use_alter).
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pipeline_versions.id", ondelete="SET NULL", use_alter=True)
    )
    # Incremented whenever any index of the collection gains, loses or replaces chunks.
    # Cached query results are keyed by it, so a change retires them without a scan.
    corpus_version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
