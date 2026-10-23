from __future__ import annotations

import contextlib
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ragkit_server.models import (
    Collection,
    Dataset,
    DatasetItem,
    EvalResult,
    EvalRun,
    PipelineVersion,
)
from ragkit_server.models.enums import RunStatus
from ragkit_server.repositories.base import Repository


class EvaluationRepository(Repository):
    # Datasets ---------------------------------------------------------------------------

    async def dataset(self, project_id: uuid.UUID, ref: str) -> Dataset | None:
        condition = Dataset.slug == ref.lower()
        with contextlib.suppress(ValueError):
            condition = Dataset.id == uuid.UUID(ref)
        result = await self.session.execute(
            select(Dataset).where(Dataset.project_id == project_id, condition)
        )
        return result.scalar_one_or_none()

    async def dataset_by_id(self, dataset_id: uuid.UUID) -> Dataset | None:
        return await self.session.get(Dataset, dataset_id)

    async def slug_taken(self, project_id: uuid.UUID, slug: str) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count()).where(Dataset.project_id == project_id, Dataset.slug == slug)
            )
        )

    async def add_dataset(self, dataset: Dataset) -> Dataset:
        self.session.add(dataset)
        await self.session.flush()
        return dataset

    async def datasets(self, project_id: uuid.UUID) -> list[tuple[Dataset, str, int]]:
        items = (
            select(func.count())
            .where(DatasetItem.dataset_id == Dataset.id)
            .correlate(Dataset)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(Dataset, Collection.slug, items)
            .join(Collection, Collection.id == Dataset.collection_id)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.name)
        )
        return [(d, slug, int(count)) for d, slug, count in result.all()]

    async def latest_runs(self, dataset_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, EvalRun]:
        if not dataset_ids:
            return {}
        latest = (
            select(EvalRun.dataset_id, func.max(EvalRun.created_at).label("created_at"))
            .where(EvalRun.dataset_id.in_(list(dataset_ids)))
            .group_by(EvalRun.dataset_id)
            .subquery()
        )
        result = await self.session.execute(
            select(EvalRun).join(
                latest,
                (latest.c.dataset_id == EvalRun.dataset_id)
                & (latest.c.created_at == EvalRun.created_at),
            )
        )
        return {run.dataset_id: run for run in result.scalars()}

    async def item_count(self, dataset_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(DatasetItem.dataset_id == dataset_id)
            )
            or 0
        )

    async def items(
        self, dataset_id: uuid.UUID, *, limit: int | None = None, offset: int = 0
    ) -> list[DatasetItem]:
        query = (
            select(DatasetItem)
            .where(DatasetItem.dataset_id == dataset_id)
            .order_by(DatasetItem.ordinal, DatasetItem.id)
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        return list((await self.session.execute(query)).scalars())

    async def item(self, dataset_id: uuid.UUID, item_id: uuid.UUID) -> DatasetItem | None:
        result = await self.session.execute(
            select(DatasetItem).where(
                DatasetItem.id == item_id, DatasetItem.dataset_id == dataset_id
            )
        )
        return result.scalar_one_or_none()

    async def items_by_ids(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, DatasetItem]:
        if not ids:
            return {}
        result = await self.session.execute(
            select(DatasetItem).where(DatasetItem.id.in_(list(ids)))
        )
        return {item.id: item for item in result.scalars()}

    async def add_items(self, dataset_id: uuid.UUID, rows: Sequence[dict[str, Any]]) -> None:
        if not rows:
            return
        start = int(
            await self.session.scalar(
                select(func.coalesce(func.max(DatasetItem.ordinal), 0)).where(
                    DatasetItem.dataset_id == dataset_id
                )
            )
            or 0
        )
        await self.session.execute(
            insert(DatasetItem),
            [
                {"dataset_id": dataset_id, "ordinal": start + i + 1, **row}
                for i, row in enumerate(rows)
            ],
        )

    async def clear_items(self, dataset_id: uuid.UUID) -> None:
        await self.session.execute(delete(DatasetItem).where(DatasetItem.dataset_id == dataset_id))

    # Runs -------------------------------------------------------------------------------

    async def add_run(self, run: EvalRun) -> EvalRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def run(self, project_id: uuid.UUID, run_id: uuid.UUID) -> EvalRun | None:
        result = await self.session.execute(
            select(EvalRun).where(EvalRun.id == run_id, EvalRun.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def runs_by_ids(self, project_id: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[EvalRun]:
        result = await self.session.execute(
            select(EvalRun).where(EvalRun.project_id == project_id, EvalRun.id.in_(list(ids)))
        )
        by_id = {run.id: run for run in result.scalars()}
        return [by_id[i] for i in ids if i in by_id]

    async def run_for_update(self, run_id: uuid.UUID) -> EvalRun | None:
        result = await self.session.execute(
            select(EvalRun).where(EvalRun.id == run_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def runs(
        self,
        project_id: uuid.UUID,
        *,
        dataset_id: uuid.UUID | None,
        collection_id: uuid.UUID | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[EvalRun], int]:
        conditions: list[Any] = [EvalRun.project_id == project_id]
        if dataset_id is not None:
            conditions.append(EvalRun.dataset_id == dataset_id)
        if collection_id is not None:
            conditions.append(EvalRun.collection_id == collection_id)
        if status:
            conditions.append(EvalRun.status == status)
        total = int(await self.session.scalar(select(func.count()).where(*conditions)) or 0)
        result = await self.session.execute(
            select(EvalRun)
            .where(*conditions)
            .order_by(EvalRun.created_at.desc(), EvalRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total

    async def run_context(
        self, runs: Sequence[EvalRun]
    ) -> tuple[dict[uuid.UUID, Dataset], dict[uuid.UUID, Collection], dict[uuid.UUID, int]]:
        """Datasets, collections and version numbers for a page of runs, in three queries."""
        dataset_ids = list({run.dataset_id for run in runs})
        collection_ids = list({run.collection_id for run in runs})
        version_ids = list({run.pipeline_version_id for run in runs})
        datasets = (
            {
                d.id: d
                for d in (
                    await self.session.execute(select(Dataset).where(Dataset.id.in_(dataset_ids)))
                ).scalars()
            }
            if dataset_ids
            else {}
        )
        collections = (
            {
                c.id: c
                for c in (
                    await self.session.execute(
                        select(Collection).where(Collection.id.in_(collection_ids))
                    )
                ).scalars()
            }
            if collection_ids
            else {}
        )
        versions = (
            {
                row.id: int(row.version)
                for row in (
                    await self.session.execute(
                        select(PipelineVersion.id, PipelineVersion.version).where(
                            PipelineVersion.id.in_(version_ids)
                        )
                    )
                ).all()
            }
            if version_ids
            else {}
        )
        return datasets, collections, versions

    async def results(
        self, run_id: uuid.UUID, *, limit: int | None = None, offset: int = 0
    ) -> list[EvalResult]:
        query = (
            select(EvalResult)
            .where(EvalResult.run_id == run_id)
            .order_by(EvalResult.ordinal, EvalResult.id)
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        return list((await self.session.execute(query)).scalars())

    async def result_count(self, run_id: uuid.UUID) -> int:
        return int(
            await self.session.scalar(select(func.count()).where(EvalResult.run_id == run_id)) or 0
        )

    async def done_item_ids(self, run_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.session.execute(
            select(EvalResult.item_id).where(EvalResult.run_id == run_id)
        )
        return {item for item in result.scalars() if item is not None}

    async def upsert_result(self, row: dict[str, Any]) -> None:
        statement = pg_insert(EvalResult).values(**row)
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=["run_id", "item_id"],
                set_={
                    key: statement.excluded[key] for key in row if key not in ("run_id", "item_id")
                },
            )
        )

    async def mark_run(self, run_id: uuid.UUID, **values: Any) -> None:
        await self.session.execute(update(EvalRun).where(EvalRun.id == run_id).values(**values))

    async def unfinished_runs_before(self, cutoff: datetime, limit: int = 50) -> list[EvalRun]:
        result = await self.session.execute(
            select(EvalRun)
            .where(
                EvalRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                EvalRun.updated_at < cutoff,
            )
            .order_by(EvalRun.updated_at)
            .limit(limit)
        )
        return list(result.scalars())
