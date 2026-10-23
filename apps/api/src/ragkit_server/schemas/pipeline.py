"""The pipeline configuration: what a pipeline version is, validated.

Every field has a default, so `{}` is a valid configuration. Index settings (cleaning,
chunking, embedding) define an index and are fingerprinted; retrieval and answer settings are
defaults a query or an evaluation run may override.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

import orjson
from pydantic import Field, model_validator

from ragkit_server.ai.embeddings import EmbeddingSpec
from ragkit_server.schemas.common import StrictModel

# Bump whenever cleaning or chunking code changes its output for the same settings, so an
# upgrade builds new indexes instead of mixing chunks from two algorithms in one.
INDEXER_VERSION = "1"

Strategy = Literal["fixed", "recursive", "sentence_window"]
Mode = Literal["vector", "keyword", "hybrid"]
Fusion = Literal["rrf", "weighted"]
Rerank = Literal["none", "lexical", "cross-encoder"]
AnswererName = Literal["extractive", "openai", "ollama"]


class CleaningConfig(StrictModel):
    normalize_unicode: bool = True
    collapse_whitespace: bool = True
    strip_boilerplate: bool = False
    drop_duplicate_blocks: bool = False
    redact_emails: bool = False
    min_block_chars: int = Field(default=0, ge=0, le=2000)


class ChunkingConfig(StrictModel):
    strategy: Strategy = "recursive"
    chunk_tokens: int = Field(default=300, ge=32, le=2048)
    overlap_tokens: int = Field(default=40, ge=0, le=1024)
    sentences_per_chunk: int = Field(default=2, ge=1, le=8)
    window_sentences: int = Field(default=2, ge=0, le=8)

    @model_validator(mode="after")
    def _overlap_fits(self) -> ChunkingConfig:
        if self.overlap_tokens > self.chunk_tokens // 2:
            raise ValueError("overlap_tokens can be at most half of chunk_tokens")
        return self

    def index_fields(self) -> dict[str, Any]:
        """Only the fields the strategy uses, so unused knobs never split an index."""
        if self.strategy == "sentence_window":
            return {
                "strategy": self.strategy,
                "sentences_per_chunk": self.sentences_per_chunk,
                "window_sentences": self.window_sentences,
                "chunk_tokens": self.chunk_tokens,
            }
        return {
            "strategy": self.strategy,
            "chunk_tokens": self.chunk_tokens,
            "overlap_tokens": self.overlap_tokens,
        }


class EmbeddingConfig(StrictModel):
    model: str = Field(default="bge-small-en-v1.5", min_length=1, max_length=200)
    provider: Literal["registry", "local", "openai", "ollama"] = "registry"
    dim: int | None = Field(default=None, ge=32, le=4096)
    contextual: bool = Field(
        default=True, description="Embed the document title and heading path with the text."
    )


class RetrievalConfig(StrictModel):
    mode: Mode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=50)
    candidates: int = Field(default=40, ge=1, le=200)
    fusion: Fusion = "rrf"
    rrf_k: int = Field(default=60, ge=1, le=1000)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    rerank: Rerank = "none"
    rerank_candidates: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _enough_candidates(self) -> RetrievalConfig:
        if self.candidates < self.top_k:
            raise ValueError("candidates must be at least top_k")
        return self


class AnswerConfig(StrictModel):
    answerer: AnswererName = "extractive"
    model: str | None = Field(default=None, max_length=200)
    max_sources: int = Field(default=5, ge=1, le=20)
    context_tokens: int = Field(default=1800, ge=100, le=32000)


class PipelineConfig(StrictModel):
    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    answer: AnswerConfig = Field(default_factory=AnswerConfig)


class RetrievalOverrides(StrictModel):
    """Per-request changes to a version's retrieval defaults. Index settings are fixed."""

    mode: Mode | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    candidates: int | None = Field(default=None, ge=1, le=200)
    fusion: Fusion | None = None
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: Rerank | None = None
    rerank_candidates: int | None = Field(default=None, ge=1, le=100)


class AnswerOverrides(StrictModel):
    answerer: AnswererName | None = None
    model: str | None = Field(default=None, max_length=200)
    max_sources: int | None = Field(default=None, ge=1, le=20)
    context_tokens: int | None = Field(default=None, ge=100, le=32000)


def apply_retrieval(base: RetrievalConfig, overrides: RetrievalOverrides | None) -> RetrievalConfig:
    if overrides is None:
        return base
    merged = {**base.model_dump(), **overrides.model_dump(exclude_none=True)}
    if overrides.top_k is not None and overrides.candidates is None:
        merged["candidates"] = max(base.candidates, overrides.top_k)
    return RetrievalConfig.model_validate(merged)


def apply_answer(base: AnswerConfig, overrides: AnswerOverrides | None) -> AnswerConfig:
    if overrides is None:
        return base
    return AnswerConfig.model_validate(
        {**base.model_dump(), **overrides.model_dump(exclude_none=True)}
    )


def index_settings(config: PipelineConfig, spec: EmbeddingSpec) -> dict[str, Any]:
    """Everything that determines an index's chunks and vectors, and nothing else."""
    return {
        "cleaning": config.cleaning.model_dump(),
        "chunking": config.chunking.index_fields(),
        "embedding": {
            "provider": spec.provider,
            "model": spec.model,
            "dim": spec.dim,
            "contextual": config.embedding.contextual,
        },
    }


def fingerprint(settings: dict[str, Any]) -> str:
    canonical = orjson.dumps(settings, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(canonical + b"|indexer:" + INDEXER_VERSION.encode()).hexdigest()
