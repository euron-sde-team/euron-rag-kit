from __future__ import annotations

from fastapi import APIRouter

from ragkit_server.api.routes import (
    analytics,
    api_keys,
    auth,
    collections,
    datasets,
    documents,
    eval_runs,
    health,
    pipelines,
    projects,
    retrieval,
)

api_router = APIRouter()
for module in (
    health,
    auth,
    projects,
    collections,
    documents,
    pipelines,
    retrieval,
    datasets,
    eval_runs,
    analytics,
    api_keys,
):
    api_router.include_router(module.router)
