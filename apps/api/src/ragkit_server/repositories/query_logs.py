from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Date, cast, func, insert, select

from ragkit_server.models import Collection, QueryLog
from ragkit_server.models.enums import QueryKind
from ragkit_server.repositories.base import Repository


class QueryLogRepository(Repository):
    async def add(self, rows: Sequence[dict[str, Any]]) -> None:
        if rows:
            await self.session.execute(insert(QueryLog), list(rows))

    async def daily(
        self, project_id: uuid.UUID, since: datetime, collection_id: uuid.UUID | None
    ) -> list[Any]:
        day = cast(func.date_trunc("day", QueryLog.created_at), Date).label("day")
        conditions = self._conditions(project_id, since, collection_id)
        result = await self.session.execute(
            select(
                day,
                func.count().filter(QueryLog.kind == QueryKind.QUERY).label("queries"),
                func.count().filter(QueryLog.kind == QueryKind.ANSWER).label("answers"),
                func.count().filter(QueryLog.hit_count == 0).label("zero_hit"),
                func.percentile_cont(0.5).within_group(QueryLog.latency_ms).label("p50"),
                func.percentile_cont(0.95).within_group(QueryLog.latency_ms).label("p95"),
            )
            .where(*conditions)
            .group_by(day)
            .order_by(day)
        )
        return list(result.all())

    async def totals(
        self, project_id: uuid.UUID, since: datetime, collection_id: uuid.UUID | None
    ) -> Any:
        conditions = self._conditions(project_id, since, collection_id)
        result = await self.session.execute(
            select(
                func.count().filter(QueryLog.kind == QueryKind.QUERY).label("queries"),
                func.count().filter(QueryLog.kind == QueryKind.ANSWER).label("answers"),
                func.count().filter(QueryLog.hit_count == 0).label("zero_hit"),
                func.count().filter(QueryLog.cached.is_(True)).label("cached"),
                func.coalesce(func.percentile_cont(0.5).within_group(QueryLog.latency_ms), 0).label(
                    "p50"
                ),
                func.coalesce(
                    func.percentile_cont(0.95).within_group(QueryLog.latency_ms), 0
                ).label("p95"),
            ).where(*conditions)
        )
        return result.one()

    async def top_queries(
        self, project_id: uuid.UUID, since: datetime, collection_id: uuid.UUID | None, limit: int
    ) -> list[Any]:
        conditions = self._conditions(project_id, since, collection_id)
        result = await self.session.execute(
            select(
                func.min(QueryLog.query_text).label("query"),
                func.count().label("times"),
                func.min(Collection.name).label("collection"),
                func.min(Collection.slug).label("collection_slug"),
            )
            .join(Collection, Collection.id == QueryLog.collection_id)
            .where(*conditions, QueryLog.query_text.is_not(None))
            .group_by(QueryLog.query_hash, QueryLog.collection_id)
            .order_by(func.count().desc(), func.min(QueryLog.query_text))
            .limit(limit)
        )
        return list(result.all())

    async def by_collection(self, project_id: uuid.UUID, since: datetime) -> list[Any]:
        result = await self.session.execute(
            select(
                Collection.slug,
                Collection.name,
                func.count(QueryLog.id).label("queries"),
                func.coalesce(
                    func.percentile_cont(0.95).within_group(QueryLog.latency_ms), 0
                ).label("p95"),
            )
            .join(Collection, Collection.id == QueryLog.collection_id)
            .where(*self._conditions(project_id, since, None))
            .group_by(Collection.slug, Collection.name)
            .order_by(func.count(QueryLog.id).desc())
        )
        return list(result.all())

    @staticmethod
    def _conditions(
        project_id: uuid.UUID, since: datetime, collection_id: uuid.UUID | None
    ) -> list[Any]:
        conditions: list[Any] = [QueryLog.project_id == project_id, QueryLog.created_at >= since]
        if collection_id is not None:
            conditions.append(QueryLog.collection_id == collection_id)
        return conditions
