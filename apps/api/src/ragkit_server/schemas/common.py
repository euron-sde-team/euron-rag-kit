from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StrictModel(BaseModel):
    """Request bodies that reject unknown fields, so a typo is an error, not a silent no-op."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Page[T](ApiModel):
    items: list[T]
    total: int
    limit: int
    offset: int
