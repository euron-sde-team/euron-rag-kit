"""Platform pieces against the real services: probes, metrics, S3 with KMS, Valkey, migrations."""

from __future__ import annotations

import uuid

import httpx
import pytest
from redis.asyncio import Redis

from ragkit_server.core.config import Settings
from ragkit_server.core.errors import NotFoundError
from ragkit_server.core.ratelimit import RateLimiter
from ragkit_server.db.migrate import migrate
from ragkit_server.integrations.storage import S3Storage
from ragkit_server.main import create_app

pytestmark = pytest.mark.integration


async def test_probes_metrics_and_capabilities(client: httpx.AsyncClient) -> None:
    assert (await client.get("/livez")).json() == {"status": "ok"}
    ready = await client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {
        "database": "ok",
        "redis": "ok",
        "storage": "ok",
        "queue": "ok",
    }
    metrics = await client.get("/metrics")
    assert "ragkit_http_requests_total" in metrics.text
    info = (await client.get("/api/v1/system/info")).json()
    assert info["answerers"] == ["extractive"]
    assert info["judge_available"] is False
    assert info["chunking_strategies"] == ["fixed", "recursive", "sentence_window"]
    assert info["supported_dims"] == [384, 768, 1024, 1536]
    models = {m["key"]: m for m in info["embedding_models"]}
    assert models["bge-small-en-v1.5"]["bundled"] is True
    assert models["openai:text-embedding-3-small"]["available"] is False
    assert "answer_relevance" in info["metrics"]


async def test_every_response_carries_a_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/info", headers={"x-request-id": "trace-me-42"})
    assert response.headers["x-request-id"] == "trace-me-42"
    missing = await client.get("/api/v1/projects/nope")
    assert missing.status_code == 401
    assert missing.json()["error"]["request_id"] == missing.headers["x-request-id"]


async def test_the_openapi_document_lists_every_route(settings: Settings) -> None:
    schema = create_app(settings).openapi()
    assert schema["info"]["title"] == "Euron RAGKit"
    assert len(schema["paths"]) == 40
    assert "/api/v1/projects/{project}/collections/{collection}/query" in schema["paths"]


async def test_migrations_are_idempotent(settings: Settings) -> None:
    await migrate(settings)
    await migrate(settings)


async def test_s3_storage_round_trip(settings: Settings) -> None:
    storage = S3Storage(settings)
    key = f"it/{uuid.uuid4()}/hello.txt"
    data = b"hello from the integration suite " * 2000
    await storage.put(key, data, "text/plain")
    assert await storage.get(key) == data
    assert b"".join([part async for part in storage.stream(key)]) == data
    await storage.delete(key)
    with pytest.raises(NotFoundError):
        await storage.get(key)
    await storage.check()


async def test_rate_limits_are_counted_in_valkey(settings: Settings) -> None:
    redis = Redis.from_url(settings.redis_url)
    try:
        limiter = RateLimiter(redis)
        key = f"it:{uuid.uuid4()}"
        results = [await limiter.hit(key, 3) for _ in range(4)]
    finally:
        await redis.aclose()
    assert [r.allowed for r in results] == [True, True, True, False]


async def test_sign_in_attempts_are_rate_limited_per_client(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"rate_limit_login": 2}))
    body = {"email": f"{uuid.uuid4().hex}@example.com", "password": "not-the-password"}
    async with app.router.lifespan_context(app):
        address = ".".join(str(b) for b in (10, *uuid.uuid4().bytes[:3]))
        transport = httpx.ASGITransport(app=app, client=(address, 4242))
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
            codes = [
                (await http.post("/api/v1/auth/login", json=body)).status_code for _ in range(3)
            ]
    assert codes == [401, 401, 429]
