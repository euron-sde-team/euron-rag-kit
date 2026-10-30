"""Query traffic for the analytics view: volume, latency, misses and what people ask."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.models import Collection, Project
from ragkit_server.repositories.query_logs import QueryLogRepository
from ragkit_server.schemas.analytics import AnalyticsOut, DayOut, TopQueryOut


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.logs = QueryLogRepository(session)

    async def overview(
        self, project: Project, *, days: int, collection: Collection | None
    ) -> AnalyticsOut:
        today = datetime.now(UTC).date()
        first = today - timedelta(days=days - 1)
        since = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
        collection_id = collection.id if collection else None
        daily = {row.day: row for row in await self.logs.daily(project.id, since, collection_id)}
        totals = await self.logs.totals(project.id, since, collection_id)
        served = int(totals.queries) + int(totals.answers)
        series = []
        for offset in range(days):
            day: date = first + timedelta(days=offset)
            row = daily.get(day)
            series.append(
                DayOut(
                    date=day,
                    queries=int(row.queries) if row else 0,
                    answers=int(row.answers) if row else 0,
                    zero_hit=int(row.zero_hit) if row else 0,
                    p50_ms=round(float(row.p50 or 0), 1) if row else 0.0,
                    p95_ms=round(float(row.p95 or 0), 1) if row else 0.0,
                )
            )
        top = await self.logs.top_queries(project.id, since, collection_id, limit=8)
        return AnalyticsOut(
            days=series,
            total_queries=int(totals.queries),
            total_answers=int(totals.answers),
            p50_ms=round(float(totals.p50), 1),
            p95_ms=round(float(totals.p95), 1),
            zero_hit_rate=round(int(totals.zero_hit) / served, 4) if served else 0.0,
            cache_hit_rate=round(int(totals.cached) / served, 4) if served else 0.0,
            top_queries=[
                TopQueryOut(
                    query=row.query,
                    count=int(row.times),
                    collection=row.collection,
                    collection_slug=row.collection_slug,
                )
                for row in top
            ],
            by_collection=[
                {
                    "slug": row.slug,
                    "name": row.name,
                    "queries": int(row.queries),
                    "p95_ms": round(float(row.p95), 1),
                }
                for row in await self.logs.by_collection(project.id, since)
            ],
        )
