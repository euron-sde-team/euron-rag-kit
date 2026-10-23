"""Embedding models behind one interface: a registry, four providers and a shared cache.

| Provider | Runs | Use |
| hash     | deterministic signed feature hashing, lexical only, no model | tests, baselines |
| local    | in process, ONNX (fastembed), no network once the model is cached | default |
| openai   | any OpenAI-compatible /embeddings endpoint | hosted |
| ollama   | an Ollama server (/api/embed) | local GPU or CPU |

Pipeline versions name a model by registry key, or name a provider, a model and its width
for anything unregistered. Every vector is L2-normalised, so cosine similarity is a dot
product everywhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, Protocol

import anyio
import httpx
import numpy as np
from redis.asyncio import Redis

from ragkit_server.core import metrics
from ragkit_server.core.config import Settings
from ragkit_server.core.errors import UnprocessableError, UpstreamError
from ragkit_server.core.logging import get_logger
from ragkit_server.core.text import content_terms
from ragkit_server.db.types import SUPPORTED_DIMS

log = get_logger("ragkit.embeddings")
Matrix = np.ndarray[Any, np.dtype[np.float32]]
Provider = Literal["hash", "local", "openai", "ollama"]


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    key: str
    provider: Provider
    model: str
    dim: int
    query_prefix: str = ""
    document_prefix: str = ""
    bundled: bool = False
    description: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.provider,
            "model": self.model,
            "dim": self.dim,
            "bundled": self.bundled,
            "description": self.description,
        }


REGISTRY: dict[str, EmbeddingSpec] = {
    spec.key: spec
    for spec in (
        EmbeddingSpec(
            "hash-384",
            "hash",
            "hash",
            384,
            bundled=True,
            description="Deterministic feature hashing of words and word pairs. Lexical only, "
            "instant, no model: a baseline and the test provider.",
        ),
        EmbeddingSpec(
            "bge-small-en-v1.5",
            "local",
            "BAAI/bge-small-en-v1.5",
            384,
            # bge v1.5 retrieves best when short queries carry this instruction.
            query_prefix="Represent this sentence for searching relevant passages: ",
            bundled=True,
            description="BAAI bge-small v1.5 on ONNX Runtime. Strong English retrieval for "
            "its size; ships in the image.",
        ),
        EmbeddingSpec(
            "all-minilm-l6-v2",
            "local",
            "sentence-transformers/all-MiniLM-L6-v2",
            384,
            description="Sentence-transformers MiniLM L6 v2. Small general-purpose model; "
            "downloaded on first use.",
        ),
        EmbeddingSpec(
            "nomic-embed-text-v1.5",
            "local",
            "nomic-ai/nomic-embed-text-v1.5-Q",
            768,
            query_prefix="search_query: ",
            document_prefix="search_document: ",
            description="Nomic embed text v1.5 (quantised), long context; downloaded on first use.",
        ),
        EmbeddingSpec(
            "openai:text-embedding-3-small",
            "openai",
            "text-embedding-3-small",
            1536,
            description="OpenAI text-embedding-3-small through any OpenAI-compatible API.",
        ),
        EmbeddingSpec(
            "ollama:nomic-embed-text",
            "ollama",
            "nomic-embed-text",
            768,
            query_prefix="search_query: ",
            document_prefix="search_document: ",
            description="nomic-embed-text served by Ollama.",
        ),
    )
}


def resolve_embedding(
    model: str, provider: str | None = None, dim: int | None = None
) -> EmbeddingSpec:
    """The spec for a pipeline's embedding settings, or a 422 explaining what is wrong."""
    if provider in (None, "registry"):
        spec = REGISTRY.get(model)
        if spec is None:
            known = ", ".join(sorted(REGISTRY))
            raise UnprocessableError(
                f"Unknown embedding model '{model}'. Use one of {known}, or set a provider "
                "(openai or ollama) and the model's dimension.",
                code="invalid_pipeline",
            )
        return spec
    if provider not in ("openai", "ollama", "local"):
        raise UnprocessableError(
            "The embedding provider must be openai, ollama or local.", code="invalid_pipeline"
        )
    if dim not in SUPPORTED_DIMS:
        widths = ", ".join(str(d) for d in SUPPORTED_DIMS)
        raise UnprocessableError(
            f"Embedding dimension must be one of {widths}.", code="invalid_pipeline"
        )
    return EmbeddingSpec(f"{provider}:{model}", provider, model, dim)  # type: ignore[arg-type]


def first_row(matrix: Matrix) -> Matrix:
    row: Matrix = matrix[0]
    return row


def normalize_rows(matrix: Matrix) -> Matrix:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized: Matrix = (matrix / norms).astype(np.float32)
    return normalized


class Embedder(Protocol):
    spec: EmbeddingSpec

    async def embed_documents(self, texts: Sequence[str]) -> Matrix: ...

    async def embed_query(self, text: str) -> Matrix: ...


class HashEmbedder:
    """Signed feature hashing of stemmed words and word pairs."""

    def __init__(self, spec: EmbeddingSpec) -> None:
        self.spec = spec

    def _vector(self, text: str) -> Matrix:
        terms = content_terms(text)
        features = Counter(terms)
        features.update({f"{a} {b}": 0.5 for a, b in pairwise(terms)})
        vector = np.zeros(self.spec.dim, dtype=np.float32)
        for feature, weight in features.items():
            digest = int.from_bytes(
                hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little"
            )
            sign = 1.0 if digest >> 63 else -1.0
            vector[digest % self.spec.dim] += (
                sign * (1 + math.log(weight)) if weight >= 1 else sign * weight
            )
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        return normalize_rows(np.stack([self._vector(t) for t in texts]).astype(np.float32))

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))


class LocalEmbedder:
    """fastembed (ONNX Runtime) in a worker thread; the model loads once per process."""

    def __init__(self, spec: EmbeddingSpec, cache_dir: Path | None, batch_size: int) -> None:
        self.spec = spec
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._batch_size = batch_size
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def _load(self) -> Any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = await anyio.to_thread.run_sync(
                        lambda: TextEmbedding(model_name=self.spec.model, cache_dir=self._cache_dir)
                    )
                    log.info("embedding_model_loaded", model=self.spec.model)
        return self._model

    async def _embed(self, texts: Sequence[str]) -> Matrix:
        model = await self._load()
        vectors = await anyio.to_thread.run_sync(
            lambda: list(model.embed(list(texts), batch_size=self._batch_size))
        )
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape[1] != self.spec.dim:
            raise UpstreamError(
                f"{self.spec.model} produced {matrix.shape[1]} dimensions, not {self.spec.dim}."
            )
        return normalize_rows(matrix)

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        return await self._embed([self.spec.document_prefix + t for t in texts])

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._embed([self.spec.query_prefix + text]))


class OpenAIEmbedder:
    def __init__(self, spec: EmbeddingSpec, base_url: str, api_key: str | None) -> None:
        self.spec = spec
        headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=60.0
        )

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        body: dict[str, Any] = {"model": self.spec.model, "input": list(texts)}
        # Only the text-embedding-3 family accepts a width; other servers may reject it.
        if self.spec.model.startswith("text-embedding-3"):
            body["dimensions"] = self.spec.dim
        try:
            response = await self._client.post("/embeddings", json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The embedding provider request failed.") from exc
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        matrix = np.asarray([item["embedding"] for item in data], dtype=np.float32)
        if matrix.shape[1] != self.spec.dim:
            raise UpstreamError(
                f"{self.spec.model} returned {matrix.shape[1]} dimensions, not {self.spec.dim}."
            )
        return normalize_rows(matrix)

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self.embed_documents([text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class OllamaEmbedder:
    def __init__(self, spec: EmbeddingSpec, url: str) -> None:
        self.spec = spec
        self._client = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=60.0)

    async def _embed(self, texts: Sequence[str]) -> Matrix:
        try:
            response = await self._client.post(
                "/api/embed", json={"model": self.spec.model, "input": list(texts)}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamError("The Ollama embedding request failed.") from exc
        matrix = np.asarray(response.json()["embeddings"], dtype=np.float32)
        if matrix.shape[1] != self.spec.dim:
            raise UpstreamError(
                f"{self.spec.model} returned {matrix.shape[1]} dimensions, not {self.spec.dim}."
            )
        return normalize_rows(matrix)

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        return await self._embed([self.spec.document_prefix + t for t in texts])

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._embed([self.spec.query_prefix + text]))

    async def aclose(self) -> None:
        await self._client.aclose()


class CachedEmbedder:
    """Read-through Redis cache keyed by model, width and the SHA-256 of the text.

    Re-indexing unchanged text with the same model, two pipeline versions sharing a model,
    or a popular query asked again costs one Redis round trip instead of a model call.
    """

    def __init__(self, inner: Embedder, redis: Redis, ttl_s: int) -> None:
        self.inner = inner
        self.spec = inner.spec
        self._redis = redis
        self._ttl = ttl_s

    def _key(self, text: str, kind: str) -> str:
        digest = hashlib.sha256(text.encode()).hexdigest()
        return f"emb:{self.spec.key}:{self.spec.dim}:{kind}:{digest}"

    async def _cached(self, texts: Sequence[str], kind: str) -> Matrix:
        if not texts:
            return np.zeros((0, self.spec.dim), dtype=np.float32)
        keys = [self._key(t, kind) for t in texts]
        try:
            stored = await self._redis.mget(keys)
        except Exception:
            stored = [None] * len(texts)
        result = np.zeros((len(texts), self.spec.dim), dtype=np.float32)
        missing = [i for i, raw in enumerate(stored) if raw is None]
        for i, raw in enumerate(stored):
            if raw is not None:
                buffer = raw.encode("latin-1") if isinstance(raw, str) else raw
                result[i] = np.frombuffer(buffer, dtype=np.float32)
        metrics.CACHE.labels("embedding", "hit").inc(len(texts) - len(missing))
        metrics.CACHE.labels("embedding", "miss").inc(len(missing))
        if missing:
            fresh = (
                await self.inner.embed_documents([texts[i] for i in missing])
                if kind == "doc"
                else np.stack([await self.inner.embed_query(texts[i]) for i in missing])
            )
            for row, i in enumerate(missing):
                result[i] = fresh[row]
            try:
                async with self._redis.pipeline(transaction=False) as pipe:
                    for row, i in enumerate(missing):
                        pipe.set(keys[i], fresh[row].tobytes(), ex=self._ttl or None)
                    await pipe.execute()
            except Exception:
                log.warning("embedding_cache_write_failed")
        return result

    async def embed_documents(self, texts: Sequence[str]) -> Matrix:
        return await self._cached(texts, "doc")

    async def embed_query(self, text: str) -> Matrix:
        return first_row(await self._cached([text], "query"))


class EmbedderPool:
    """One embedder per model per process, created on first use and cached in Redis."""

    def __init__(self, settings: Settings, redis: Redis) -> None:
        self._settings = settings
        self._redis = redis
        self._embedders: dict[str, CachedEmbedder] = {}
        self._closers: list[Any] = []

    def availability(self, spec: EmbeddingSpec) -> str | None:
        """Why this deployment cannot use the model, or None when it can."""
        if spec.provider == "openai" and not self._settings.embeddings_api_key:
            return (
                "Set EMBEDDINGS_API_KEY (and EMBEDDINGS_API_BASE) to use OpenAI-compatible "
                "embeddings."
            )
        return None

    def get(self, spec: EmbeddingSpec) -> CachedEmbedder:
        cached = self._embedders.get(spec.key)
        if cached is not None:
            return cached
        inner: Embedder
        settings = self._settings
        match spec.provider:
            case "hash":
                inner = HashEmbedder(spec)
            case "openai":
                key = settings.embeddings_api_key
                openai = OpenAIEmbedder(
                    spec, settings.embeddings_api_base, key.get_secret_value() if key else None
                )
                self._closers.append(openai.aclose)
                inner = openai
            case "ollama":
                ollama = OllamaEmbedder(spec, settings.ollama_url)
                self._closers.append(ollama.aclose)
                inner = ollama
            case _:
                inner = LocalEmbedder(
                    spec, settings.embeddings_cache_dir, settings.embeddings_batch_size
                )
        cached = CachedEmbedder(inner, self._redis, settings.embedding_cache_ttl_s)
        self._embedders[spec.key] = cached
        return cached

    async def warm_up(self, keys: Sequence[str]) -> None:
        for key in keys:
            spec = REGISTRY.get(key)
            if spec is not None and spec.provider == "local":
                try:
                    await self.get(spec).inner.embed_query("warm up")
                except Exception as exc:
                    log.warning("embedding_warm_up_failed", model=key, error=str(exc))

    async def aclose(self) -> None:
        for closer in self._closers:
            await closer()
