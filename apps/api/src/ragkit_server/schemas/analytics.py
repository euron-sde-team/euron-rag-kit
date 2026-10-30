from __future__ import annotations

from datetime import date

from ragkit_server.schemas.common import ApiModel


class DayOut(ApiModel):
    date: date
    queries: int
    answers: int
    zero_hit: int
    p50_ms: float
    p95_ms: float


class TopQueryOut(ApiModel):
    query: str
    count: int
    collection: str
    collection_slug: str


class AnalyticsOut(ApiModel):
    days: list[DayOut]
    total_queries: int
    total_answers: int
    p50_ms: float
    p95_ms: float
    zero_hit_rate: float
    cache_hit_rate: float
    top_queries: list[TopQueryOut]
    by_collection: list[dict[str, object]]
