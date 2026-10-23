from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from ragkit_server.evaluation.metrics import METRICS
from ragkit_server.schemas.common import ApiModel, StrictModel
from ragkit_server.schemas.pipeline import AnswerOverrides, RetrievalOverrides


class ExpectedSourceIn(StrictModel):
    document: str = Field(min_length=1, max_length=200, description="A document's external id.")
    evidence: str | None = Field(default=None, max_length=2000)


class ItemIn(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    expected_sources: list[ExpectedSourceIn] = Field(default_factory=list, max_length=20)
    expected_answer: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = [tag.strip().lower()[:40] for tag in tags if tag.strip()]
        return list(dict.fromkeys(cleaned))


class GateSettings(StrictModel):
    min: dict[str, float] = Field(default_factory=dict, description="Floors, by metric.")
    max_drop: float | None = Field(
        default=None, ge=0, le=1, description="Largest allowed drop against the baseline run."
    )

    @field_validator("min")
    @classmethod
    def _known_metrics(cls, floors: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(floors) - set(METRICS))
        if unknown:
            raise ValueError(f"unknown metric {unknown[0]}; use one of {', '.join(METRICS)}")
        return floors


class DatasetCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    collection: str = Field(min_length=1, max_length=64, description="Collection slug or id.")
    description: str = Field(default="", max_length=2000)
    gate: GateSettings = Field(default_factory=GateSettings)
    items: list[ItemIn] = Field(default_factory=list, max_length=2000)


class DatasetUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    gate: GateSettings | None = None


class ItemsImport(StrictModel):
    items: list[ItemIn] = Field(min_length=1, max_length=2000)
    replace: bool = Field(default=False, description="Remove existing items first.")


class DatasetOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    collection_id: uuid.UUID
    collection_slug: str
    item_count: int
    gate: dict[str, Any]
    baseline_run_id: uuid.UUID | None
    last_run: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ItemOut(ApiModel):
    id: uuid.UUID
    ordinal: int
    question: str
    expected_sources: list[dict[str, Any]]
    expected_answer: str | None
    tags: list[str]


class RunCreate(StrictModel):
    dataset: str = Field(min_length=1, max_length=64, description="Dataset slug or id.")
    pipeline_version: int | None = Field(default=None, ge=1, description="Defaults to active.")
    label: str | None = Field(default=None, max_length=160)
    k: int = Field(default=5, ge=1, le=50)
    grader: Literal["deterministic", "model"] = "deterministic"
    answers: bool = Field(default=True, description="Generate and grade answers too.")
    retrieval: RetrievalOverrides | None = None
    answer: AnswerOverrides | None = None


class RunOut(ApiModel):
    id: uuid.UUID
    label: str
    status: str
    dataset: dict[str, Any]
    collection: dict[str, Any]
    pipeline_version: int
    k: int
    grader: str
    config: dict[str, Any]
    total_items: int
    completed_items: int
    metrics: dict[str, Any]
    error: str | None
    is_baseline: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class ResultOut(ApiModel):
    id: uuid.UUID
    item_id: uuid.UUID | None
    ordinal: int
    question: str
    tags: list[str]
    retrieved: list[dict[str, Any]]
    answer: str | None
    citations: list[dict[str, Any]]
    metrics: dict[str, Any]
    grading: dict[str, Any]
    expected_sources: list[dict[str, Any]] = Field(default_factory=list)
    expected_answer: str | None = None
    latency_ms: int
    retrieval_ms: int
    answer_ms: int
    error: str | None


class GateRequest(StrictModel):
    baseline_run_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the dataset's baseline run."
    )
    min: dict[str, float] | None = None
    max_drop: float | dict[str, float] | None = None


class GateCheckOut(ApiModel):
    metric: str
    kind: str
    threshold: float
    value: float | None
    baseline: float | None
    passed: bool
    message: str


class GateOut(ApiModel):
    passed: bool
    run_id: uuid.UUID
    run_status: str
    baseline_run_id: uuid.UUID | None
    checks: list[GateCheckOut]


class ComparisonOut(ApiModel):
    runs: list[RunOut]
    reference_run: uuid.UUID
    same_dataset: bool
    metrics: list[dict[str, Any]]
    config_diff: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    summary: dict[str, int]
