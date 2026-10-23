from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from ragkit_server.schemas.common import ApiModel, StrictModel
from ragkit_server.schemas.pipeline import AnswererName, Fusion, Mode, Rerank


class QueryRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    pipeline_version: int | None = Field(
        default=None, ge=1, description="Defaults to the collection's active version."
    )
    filters: dict[str, Any] | None = Field(
        default=None, description='Metadata filter, for example {"section": "guides"}.'
    )
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    mode: Mode | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    candidates: int | None = Field(default=None, ge=1, le=200)
    fusion: Fusion | None = None
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: Rerank | None = None
    rerank_candidates: int | None = Field(default=None, ge=1, le=100)
    use_cache: bool = True


class AnswerRequest(QueryRequest):
    answerer: AnswererName | None = None
    model: str | None = Field(default=None, max_length=200)
    max_sources: int | None = Field(default=None, ge=1, le=20)
    context_tokens: int | None = Field(default=None, ge=100, le=32000)


class HitOut(ApiModel):
    rank: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    external_id: str
    location: str
    heading: str
    text: str
    context: str | None
    metadata: dict[str, Any]
    score: float
    scores: dict[str, float | None]
    ranks: dict[str, int | None]


class RerankInfo(ApiModel):
    kind: str
    fallback: bool


class QueryResponse(ApiModel):
    query: str
    pipeline_version: int
    index_id: uuid.UUID
    index_status: str
    mode: str
    fusion: str | None
    rerank: RerankInfo
    hits: list[HitOut]
    candidates: dict[str, int] = Field(description="How many candidates each stage produced.")
    timings_ms: dict[str, float]
    cached: bool


class CitationOut(ApiModel):
    n: int
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    external_id: str
    location: str
    quote: str


class UsageOut(ApiModel):
    prompt_tokens: int
    completion_tokens: int


class AnswerResponse(ApiModel):
    query: str
    answer: str
    answerer: str
    citations: list[CitationOut]
    sources: list[HitOut]
    usage: UsageOut
    retrieval: QueryResponse
    timings_ms: dict[str, float]
