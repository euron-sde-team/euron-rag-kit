"""Query traffic analytics for a project, optionally for one collection."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from ragkit_server.api.deps import ContainerDep, SessionDep, ViewerDep
from ragkit_server.schemas.analytics import AnalyticsOut
from ragkit_server.services.analytics import AnalyticsService
from ragkit_server.services.collections import CollectionService

router = APIRouter(prefix="/api/v1/projects/{project}/analytics", tags=["analytics"])


@router.get("", summary="Queries per day, latency, zero-hit rate and top queries")
async def analytics(
    ctx: ViewerDep,
    container: ContainerDep,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    collection: Annotated[str | None, Query(max_length=64)] = None,
) -> AnalyticsOut:
    scope = (
        await CollectionService(container, session).get(ctx.project, collection)
        if collection
        else None
    )
    return await AnalyticsService(session).overview(ctx.project, days=days, collection=scope)
