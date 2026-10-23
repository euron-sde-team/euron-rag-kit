"""Probes, metrics and public deployment capabilities."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ragkit_server import __version__
from ragkit_server.ai.embeddings import REGISTRY
from ragkit_server.api.deps import ContainerDep, SessionDep
from ragkit_server.core.logging import get_logger
from ragkit_server.db.types import SUPPORTED_DIMS
from ragkit_server.evaluation.metrics import METRICS
from ragkit_server.ingestion.sniff import EXTENSIONS
from ragkit_server.repositories.users import UserRepository
from ragkit_server.schemas.system import RerankerInfo, SystemInfo

router = APIRouter()
log = get_logger("ragkit.health")


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(container: ContainerDep) -> JSONResponse:
    checks: dict[str, Any] = {}
    for name, probe in (
        ("database", container.db.ping),
        ("redis", container.redis.ping),
        ("storage", container.storage.check),
        ("queue", container.queue.check),
    ):
        try:
            await probe()
            checks[name] = "ok"
        except Exception as exc:
            log.warning("readiness_check_failed", check=name, error=type(exc).__name__)
            checks[name] = "failing"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ready" if ready else "degraded", "checks": checks},
        status_code=200 if ready else 503,
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/system/info", tags=["system"], summary="Deployment capabilities and limits")
async def system_info(container: ContainerDep, session: SessionDep) -> SystemInfo:
    settings = container.settings
    rerankers = container.rerankers
    models = []
    for spec in REGISTRY.values():
        problem = container.embedders.availability(spec)
        models.append({**spec.public(), "available": problem is None, "reason": problem})
    return SystemInfo(
        product_name=settings.product_name,
        version=__version__,
        embedding_models=models,
        default_embedding_model=settings.default_embedding_model,
        reranker=RerankerInfo(
            model=rerankers.cross_encoder.model_name,
            available=rerankers.cross_encoder_error is None,
            error=rerankers.cross_encoder_error,
        ),
        answerers=container.answerers.available(),
        judge_available=container.judge is not None,
        chunking_strategies=["fixed", "recursive", "sentence_window"],
        supported_dims=list(SUPPORTED_DIMS),
        metrics=list(METRICS),
        max_upload_mb=settings.max_upload_mb,
        accepted_extensions=sorted(EXTENSIONS),
        allow_signup=settings.allow_signup,
        needs_setup=await UserRepository(session).count() == 0,
    )
