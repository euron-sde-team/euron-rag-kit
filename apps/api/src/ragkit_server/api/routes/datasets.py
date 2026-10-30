"""Evaluation datasets: questions with expected sources and reference answers."""

from __future__ import annotations

import uuid
from typing import Annotated

import orjson
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse

from ragkit_server.api.deps import ContainerDep, EditorDep, SessionDep, ViewerDep
from ragkit_server.models import Dataset
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.evaluation import (
    DatasetCreate,
    DatasetOut,
    DatasetUpdate,
    ItemOut,
    ItemsImport,
)
from ragkit_server.services.evaluation import EvaluationService

router = APIRouter(prefix="/api/v1/projects/{project}/datasets", tags=["evaluation"])


async def _dataset(
    dataset: str, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> Dataset:
    return await EvaluationService(container, session).dataset(ctx.project, dataset)


DatasetDep = Annotated[Dataset, Depends(_dataset)]


@router.get("", summary="Datasets with question counts and their latest run")
async def list_datasets(
    ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> list[DatasetOut]:
    return await EvaluationService(container, session).datasets(ctx.project)


@router.post("", summary="Create a dataset, optionally with questions", status_code=201)
async def create_dataset(
    body: DatasetCreate, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> DatasetOut:
    service = EvaluationService(container, session)
    dataset = await service.create_dataset(ctx.project, ctx.principal, body)
    return await service.dataset_out(ctx.project, dataset)


@router.get("/{dataset}", summary="A dataset")
async def get_dataset(
    dataset: DatasetDep, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> DatasetOut:
    return await EvaluationService(container, session).dataset_out(ctx.project, dataset)


@router.patch("/{dataset}", summary="Rename a dataset or change its gate thresholds")
async def update_dataset(
    dataset: str, body: DatasetUpdate, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> DatasetOut:
    service = EvaluationService(container, session)
    found = await service.dataset(ctx.project, dataset)
    updated = await service.update_dataset(ctx.project, found, ctx.principal, body)
    return await service.dataset_out(ctx.project, updated)


@router.delete("/{dataset}", summary="Delete a dataset and its runs", status_code=204)
async def delete_dataset(
    dataset: str, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = EvaluationService(container, session)
    await service.delete_dataset(
        ctx.project, await service.dataset(ctx.project, dataset), ctx.principal
    )


@router.get("/{dataset}/items", summary="The questions of a dataset")
async def list_items(
    dataset: DatasetDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ItemOut]:
    items, total = await EvaluationService(container, session).items(
        dataset, limit=limit, offset=offset
    )
    return Page[ItemOut](
        items=[ItemOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "/{dataset}/items", summary="Add (or replace) questions", status_code=status.HTTP_201_CREATED
)
async def import_items(
    dataset: str, body: ItemsImport, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> DatasetOut:
    service = EvaluationService(container, session)
    found = await service.dataset(ctx.project, dataset)
    await service.import_items(ctx.project, found, ctx.principal, body)
    return await service.dataset_out(ctx.project, found)


@router.get(
    "/{dataset}/export",
    summary="The questions as JSONL, ready to import elsewhere",
    response_class=PlainTextResponse,
)
async def export_items(
    dataset: DatasetDep, container: ContainerDep, session: SessionDep
) -> PlainTextResponse:
    items, _ = await EvaluationService(container, session).items(dataset, limit=10_000, offset=0)
    lines = [
        orjson.dumps(
            {
                "question": item.question,
                "expected_sources": item.expected_sources,
                "expected_answer": item.expected_answer,
                "tags": item.tags,
            }
        ).decode()
        for item in items
    ]
    return PlainTextResponse(
        "\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
        headers={"content-disposition": f'attachment; filename="{dataset.slug}.jsonl"'},
    )


@router.delete("/{dataset}/items/{item_id}", summary="Remove a question", status_code=204)
async def delete_item(
    dataset: str, item_id: uuid.UUID, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = EvaluationService(container, session)
    found = await service.dataset(ctx.project, dataset)
    await service.delete_item(ctx.project, found, ctx.principal, item_id)
