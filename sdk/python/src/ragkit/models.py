"""Typed views of the API's responses.

Models accept fields the SDK does not know yet (`extra="allow"`), so a newer server never
breaks an older SDK; fields the SDK documents are typed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Collection(Model):
    id: str
    slug: str
    name: str
    description: str = ""
    active_version: int | None = None
    version_count: int = 0
    document_count: int = 0
    ready_documents: int = 0
    chunk_count: int = 0


class Document(Model):
    id: str
    external_id: str
    title: str
    source_type: str
    source_uri: str | None = None
    kind: str | None = None
    status: str
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    section_count: int = 0
    token_count: int = 0
    created_at: datetime


class Rejected(Model):
    name: str
    code: str
    message: str


class IngestResult(Model):
    created: list[Document]
    duplicates: list[Document]
    rejected: list[Rejected]


class IndexProgress(Model):
    total: int
    ready: int
    processing: int
    queued: int
    failed: int


class Index(Model):
    id: str
    fingerprint: str
    embedding_model: str
    embedding_dim: int
    status: str
    progress: IndexProgress
    chunk_count: int
    token_count: int
    shared_with: list[int] = Field(default_factory=list)


class PipelineVersion(Model):
    id: str
    version: int
    name: str
    description: str = ""
    config: dict[str, Any]
    active: bool
    index: Index
    created_at: datetime


class Hit(Model):
    rank: int
    chunk_id: str
    document_id: str
    document_title: str
    external_id: str
    location: str
    heading: str
    text: str
    context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
    scores: dict[str, float | None]
    ranks: dict[str, int | None]

    @property
    def passage(self) -> str:
        """The sentence window when there is one, else the chunk text."""
        return self.context or self.text


class QueryResult(Model):
    query: str
    pipeline_version: int
    index_id: str
    index_status: str
    mode: str
    fusion: str | None = None
    rerank: dict[str, Any]
    hits: list[Hit]
    candidates: dict[str, int]
    timings_ms: dict[str, float]
    cached: bool


class Citation(Model):
    n: int
    chunk_id: str
    document_id: str
    document_title: str
    external_id: str
    location: str
    quote: str


class Answer(Model):
    query: str
    answer: str
    answerer: str
    citations: list[Citation]
    sources: list[Hit]
    usage: dict[str, int]
    retrieval: QueryResult
    timings_ms: dict[str, float]


class Dataset(Model):
    id: str
    slug: str
    name: str
    description: str = ""
    collection_slug: str
    item_count: int
    gate: dict[str, Any] = Field(default_factory=dict)
    baseline_run_id: str | None = None


class Run(Model):
    id: str
    label: str
    status: str
    dataset: dict[str, Any]
    collection: dict[str, Any]
    pipeline_version: int
    k: int
    grader: str
    total_items: int
    completed_items: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    is_baseline: bool = False
    created_at: datetime
    duration_ms: int | None = None

    @property
    def finished(self) -> bool:
        return self.status in ("completed", "failed")

    @property
    def means(self) -> dict[str, float]:
        means: dict[str, float] = self.metrics.get("means", {})
        return means


class RunResult(Model):
    id: str
    ordinal: int
    question: str
    tags: list[str] = Field(default_factory=list)
    retrieved: list[dict[str, Any]] = Field(default_factory=list)
    answer: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None


class Comparison(Model):
    runs: list[Run]
    reference_run: str
    same_dataset: bool
    metrics: list[dict[str, Any]]
    config_diff: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    summary: dict[str, int]


class GateCheck(Model):
    metric: str
    kind: str
    threshold: float
    value: float | None = None
    baseline: float | None = None
    passed: bool
    message: str


class GateResult(Model):
    passed: bool
    run_id: str
    run_status: str
    baseline_run_id: str | None = None
    checks: list[GateCheck]
