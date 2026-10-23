from __future__ import annotations

from typing import Any

from ragkit_server.schemas.common import ApiModel


class RerankerInfo(ApiModel):
    model: str
    available: bool
    error: str | None


class SystemInfo(ApiModel):
    product_name: str
    version: str
    embedding_models: list[dict[str, Any]]
    default_embedding_model: str
    reranker: RerankerInfo
    answerers: list[str]
    judge_available: bool
    chunking_strategies: list[str]
    supported_dims: list[int]
    metrics: list[str]
    max_upload_mb: int
    accepted_extensions: list[str]
    allow_signup: bool
    needs_setup: bool
