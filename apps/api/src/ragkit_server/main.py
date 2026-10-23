"""The FastAPI application factory.

uvicorn ragkit_server.main:create_app --factory --port 8160
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ragkit_server import __version__
from ragkit_server.api.router import api_router
from ragkit_server.core.config import Settings, get_settings
from ragkit_server.core.context import BodySizeLimitMiddleware, RequestContextMiddleware
from ragkit_server.core.errors import install_exception_handlers
from ragkit_server.core.logging import configure_logging, get_logger
from ragkit_server.db.migrate import migrate
from ragkit_server.integrations.queue import InlineQueue
from ragkit_server.services.container import build_container
from ragkit_server.services.ingestion import IngestionService

log = get_logger("ragkit.app")

DESCRIPTION = """
Build, measure and serve retrieval pipelines.

Authenticate with the session cookie set by `POST /api/v1/auth/login`, or with
`Authorization: Bearer <token>` using a session token or a project API key (`rgk_...`).
Every error uses one envelope: `{"error": {"code", "message", "request_id", "details?"}}`.
"""

TAGS = [
    {"name": "auth", "description": "Sign-in, sign-up, sessions and your profile."},
    {"name": "projects", "description": "Projects, members, roles and the activity trail."},
    {"name": "collections", "description": "Corpora with documents, versions and datasets."},
    {"name": "documents", "description": "Files, URLs and text: intake and the library."},
    {
        "name": "pipelines",
        "description": "Immutable pipeline versions, shared indexes, chunks and previews.",
    },
    {"name": "retrieval", "description": "Hybrid retrieval with reranking, and cited answers."},
    {
        "name": "evaluation",
        "description": "Datasets, runs, metrics, side-by-side comparison and the CI gate.",
    },
    {"name": "analytics", "description": "Query traffic, latency and misses."},
    {"name": "api keys", "description": "Project-scoped keys for applications and CI."},
    {"name": "system", "description": "Deployment capabilities and limits."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.is_production and (problems := settings.production_problems()):
        raise RuntimeError("Refusing to start in production:\n  - " + "\n  - ".join(problems))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_boot:
            await migrate(settings)
        container = build_container(settings)
        if isinstance(container.queue, InlineQueue):
            container.queue.bind(IngestionService(container).handle)
        app.state.container = container
        # Load the local models in the background so the first query is not the slow one.
        warm_up = asyncio.create_task(container.warm_up())
        log.info(
            "started",
            version=__version__,
            env=settings.app_env,
            answerers=container.answerers.available(),
            queue=settings.queue_backend,
            storage=settings.storage_backend,
        )
        try:
            yield
        finally:
            warm_up.cancel()
            if isinstance(container.queue, InlineQueue):
                await container.queue.drain()
            await container.close()

    app = FastAPI(
        title=settings.product_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
        license_info={"name": "MIT", "identifier": "MIT"},
    )
    install_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "x-request-id"],
        expose_headers=[
            "x-request-id",
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset",
            "content-disposition",
        ],
        max_age=600,
    )
    # Twenty files per upload request, each up to the per-file limit, plus form overhead.
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes * 20 + 1024 * 1024
    )
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
    app.include_router(api_router)
    return app
