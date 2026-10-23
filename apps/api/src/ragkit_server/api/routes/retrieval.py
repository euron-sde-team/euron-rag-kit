"""Serving: retrieval and cited answers over a collection's pipeline version."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ragkit_server.api.deps import CollectionViewerDep, ContainerDep, SessionDep, rate_limit
from ragkit_server.schemas.retrieval import (
    AnswerRequest,
    AnswerResponse,
    QueryRequest,
    QueryResponse,
)
from ragkit_server.services.retrieval import RetrievalService

router = APIRouter(
    prefix="/api/v1/projects/{project}/collections/{collection}",
    tags=["retrieval"],
    dependencies=[Depends(rate_limit("query", "rate_limit_query"))],
)


@router.post("/query", summary="Retrieve passages (vector, keyword or hybrid, with reranking)")
async def query(
    body: QueryRequest, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> QueryResponse:
    return await RetrievalService(container, session).query(
        ctx.project, ctx.collection, body, ctx.principal
    )


@router.post("/answer", summary="Retrieve, then answer with verified citations")
async def answer(
    body: AnswerRequest, ctx: CollectionViewerDep, container: ContainerDep, session: SessionDep
) -> AnswerResponse:
    return await RetrievalService(container, session).answer(
        ctx.project, ctx.collection, body, ctx.principal
    )
