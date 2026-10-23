import fakeredis
import numpy as np
import pytest

from ragkit_server.ai.embeddings import (
    REGISTRY,
    CachedEmbedder,
    EmbedderPool,
    HashEmbedder,
    resolve_embedding,
)
from ragkit_server.core.config import Settings
from ragkit_server.core.errors import UnprocessableError

HASH = REGISTRY["hash-384"]


async def test_hash_embeddings_are_deterministic_unit_vectors() -> None:
    embedder = HashEmbedder(HASH)
    first = await embedder.embed_documents(["Refunds take five business days", "Webhook retries"])
    again = await embedder.embed_documents(["Refunds take five business days", "Webhook retries"])
    assert first.shape == (2, 384)
    assert np.allclose(first, again)
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0)


async def test_hash_embeddings_reward_shared_words() -> None:
    embedder = HashEmbedder(HASH)
    query = await embedder.embed_query("how long do refunds take")
    close, far = await embedder.embed_documents(
        ["Refunds take five business days to arrive.", "Webhook endpoints must answer quickly."]
    )
    assert float(query @ close) > float(query @ far)


def test_registry_resolution_and_custom_models() -> None:
    assert resolve_embedding("bge-small-en-v1.5").dim == 384
    custom = resolve_embedding("mxbai-embed-large", "ollama", 1024)
    assert (custom.key, custom.provider, custom.dim) == ("ollama:mxbai-embed-large", "ollama", 1024)
    with pytest.raises(UnprocessableError):
        resolve_embedding("no-such-model")
    with pytest.raises(UnprocessableError):
        resolve_embedding("custom", "openai", 999)
    with pytest.raises(UnprocessableError):
        resolve_embedding("custom", "carrier-pigeon", 384)


async def test_the_cache_serves_repeats_without_calling_the_model() -> None:
    calls: list[int] = []

    class Counting(HashEmbedder):
        async def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            calls.append(len(texts))
            return await super().embed_documents(texts)

    cached = CachedEmbedder(Counting(HASH), fakeredis.FakeAsyncRedis(), ttl_s=60)
    first = await cached.embed_documents(["alpha beta", "gamma delta"])
    second = await cached.embed_documents(["gamma delta", "alpha beta", "epsilon"])
    assert calls == [2, 1]
    assert np.allclose(first[0], second[1])


def test_the_pool_reuses_embedders_and_reports_missing_credentials() -> None:
    pool = EmbedderPool(Settings(), fakeredis.FakeAsyncRedis())
    assert pool.get(HASH) is pool.get(HASH)
    assert pool.availability(REGISTRY["openai:text-embedding-3-small"]) is not None
    assert pool.availability(HASH) is None
