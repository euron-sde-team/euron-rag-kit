from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from ragkit_server.schemas.common import ApiModel, StrictModel
from ragkit_server.schemas.pipeline import PipelineConfig


class CollectionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    description: str = Field(default="", max_length=2000)
    pipeline: PipelineConfig | None = Field(
        default=None, description="Configuration of version 1. Defaults apply when omitted."
    )


class CollectionUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class CollectionOut(ApiModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    active_version: int | None
    version_count: int
    document_count: int
    ready_documents: int
    chunk_count: int
    corpus_version: int
    created_at: datetime
    updated_at: datetime
