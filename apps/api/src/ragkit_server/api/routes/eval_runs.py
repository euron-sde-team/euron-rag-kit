"""Evaluation runs (experiments): start, follow, inspect, compare and gate."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from ragkit_server.api.deps import ContainerDep, EditorDep, SessionDep, ViewerDep, rate_limit
from ragkit_server.core.errors import UnprocessableError
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.evaluation import (
    ComparisonOut,
    GateOut,
    GateRequest,
    ResultOut,
    RunCreate,
    RunOut,
)
from ragkit_server.services.evaluation import EvaluationService

router = APIRouter(prefix="/api/v1/projects/{project}/eval-runs", tags=["evaluation"])


@router.get("", summary="Runs, newest first")
async def list_runs(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    dataset: Annotated[str | None, Query(max_length=64)] = None,
    collection: Annotated[str | None, Query(max_length=64)] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(queued|running|completed|failed)$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RunOut]:
    return await EvaluationService(container, session).list_runs(
        ctx.project,
        dataset=dataset,
        collection=collection,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    summary="Start a run of a dataset against a pipeline version",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("eval", "rate_limit_eval"))],
)
async def create_run(
    body: RunCreate, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> RunOut:
    service = EvaluationService(container, session)
    run = await service.create_run(ctx.project, ctx.principal, body)
    return (await service.runs_out([run]))[0]


@router.get("/compare", summary="Compare two to four runs side by side")
async def compare_runs(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    ids: Annotated[str, Query(description="Comma-separated run ids; the first is the reference.")],
) -> ComparisonOut:
    try:
        run_ids = [uuid.UUID(part.strip()) for part in ids.split(",") if part.strip()]
    except ValueError as exc:
        raise UnprocessableError("ids must be comma-separated run ids.") from exc
    return await EvaluationService(container, session).compare(ctx.project, run_ids)


@router.get("/{run_id}", summary="A run with its aggregate metrics and progress")
async def get_run(
    run_id: uuid.UUID, ctx: ViewerDep, container: ContainerDep, session: SessionDep
) -> RunOut:
    service = EvaluationService(container, session)
    return (await service.runs_out([await service.run(ctx.project, run_id)]))[0]


@router.get("/{run_id}/results", summary="Per-question results")
async def run_results(
    run_id: uuid.UUID,
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ResultOut]:
    service = EvaluationService(container, session)
    run = await service.run(ctx.project, run_id)
    return await service.results(run, limit=limit, offset=offset)


@router.post("/{run_id}/gate", summary="Check a run against floors and its baseline")
async def gate_run(
    run_id: uuid.UUID,
    body: GateRequest,
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
) -> GateOut:
    service = EvaluationService(container, session)
    return await service.gate(ctx.project, await service.run(ctx.project, run_id), body)


@router.post("/{run_id}/baseline", summary="Make this run its dataset's baseline")
async def set_baseline(
    run_id: uuid.UUID, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> RunOut:
    service = EvaluationService(container, session)
    run = await service.set_baseline(
        ctx.project, await service.run(ctx.project, run_id), ctx.principal
    )
    return (await service.runs_out([run]))[0]


@router.delete("/{run_id}", summary="Delete a finished run", status_code=204)
async def delete_run(
    run_id: uuid.UUID, ctx: EditorDep, container: ContainerDep, session: SessionDep
) -> None:
    service = EvaluationService(container, session)
    await service.delete_run(ctx.project, await service.run(ctx.project, run_id), ctx.principal)
