from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from ragkit_server.schemas.common import ApiModel, StrictModel
from ragkit_server.schemas.pipeline import ChunkingConfig, CleaningConfig, PipelineConfig


class PipelineCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    config: PipelineConfig = Field(default_factory=PipelineConfig)
    activate: bool = Field(default=False, description="Make it the active version now.")


class IndexProgress(ApiModel):
    total: int
    ready: int
    processing: int
    queued: int
    failed: int


class IndexOut(ApiModel):
    id: uuid.UUID
    fingerprint: str
    embedding_model: str
    embedding_dim: int
    status: str
    progress: IndexProgress
    chunk_count: int
    token_count: int
    shared_with: list[int] = Field(description="Other versions that use this index.")


class PipelineVersionOut(ApiModel):
    id: uuid.UUID
    version: int
    name: str
    description: str
    config: dict[str, Any]
    active: bool
    index: IndexOut
    created_at: datetime


class ChunkOut(ApiModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    ordinal: int
    heading: str
    location: str
    text: str
    context: str | None
    token_count: int


class ChunkStats(ApiModel):
    count: int
    mean_tokens: float
    min_tokens: int
    max_tokens: int
    histogram: list[dict[str, int]] = Field(description="Chunks per token-count bucket.")


class PreviewRequest(StrictModel):
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    document_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=200_000)


class PreviewOut(ApiModel):
    chunks: list[dict[str, Any]]
    stats: ChunkStats
    cleaning: dict[str, Any]
