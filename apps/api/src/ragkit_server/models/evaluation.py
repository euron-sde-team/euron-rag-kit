from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ragkit_server.db.base import Base, IdMixin, TimestampMixin


class Dataset(IdMixin, TimestampMixin, Base):
    """Questions with expected sources and reference answers, for one collection."""

    __tablename__ = "datasets"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    slug: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    # Default thresholds for `ragkit eval gate`: {"min": {metric: floor}, "max_drop": 0.02}.
    gate: Mapped[dict[str, Any]] = mapped_column(default=dict)
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="SET NULL", use_alter=True)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class DatasetItem(IdMixin, Base):
    __tablename__ = "dataset_items"

    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    ordinal: Mapped[int]
    question: Mapped[str] = mapped_column(Text)
    # [{"document": "<external_id>", "evidence": "quoted text" | null}]
    expected_sources: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EvalRun(IdMixin, Base):
    """One dataset measured against one pipeline version: an experiment."""

    __tablename__ = "eval_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE")
    )
    pipeline_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_versions.id", ondelete="CASCADE")
    )
    label: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16))
    # Everything that determined the result: the version's configuration with the run's
    # overrides applied, k, the grader and whether answers were generated.
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    k: Mapped[int]
    grader: Mapped[str] = mapped_column(String(16))
    total_items: Mapped[int] = mapped_column(default=0)
    completed_items: Mapped[int] = mapped_column(default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class EvalResult(IdMixin, Base):
    """One question of a run: what was retrieved, the answer, and every metric."""

    __tablename__ = "eval_results"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"))
    # Results are history: deleting an item later keeps them, with the question copied here.
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_items.id", ondelete="SET NULL")
    )
    ordinal: Mapped[int]
    question: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    retrieved: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict)
    grading: Mapped[dict[str, Any]] = mapped_column(default=dict)
    latency_ms: Mapped[int] = mapped_column(default=0)
    retrieval_ms: Mapped[int] = mapped_column(default=0)
    answer_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
