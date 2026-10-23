"""Second-stage reranking of fused candidates.

- `cross-encoder`: a local cross-encoder (fastembed ONNX, `Xenova/ms-marco-MiniLM-L-6-v2`
  by default) reads the query and each passage together. Slower than the first stage, far
  better at telling the right passage from a merely similar one.
- `lexical`: deterministic, no model. BM25 over the candidate set, plus bonuses for query
  bigrams in order, for query words in the chunk's heading, and for code-like identifiers
  from the query (`ACME-4011`, `max_retries`) that appear verbatim. Also the fallback when
  the cross-encoder cannot be loaded.

Scores are returned in [0, 1] (the cross-encoder's logits through a sigmoid), so callers can
show them; ordering is by the raw score.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any, Protocol

import anyio

from ragkit_server.core import metrics
from ragkit_server.core.logging import get_logger
from ragkit_server.core.text import content_terms, identifiers
from ragkit_server.retrieval.types import Hit

log = get_logger("ragkit.rerank")

BM25_K1 = 1.2
BM25_B = 0.75
BIGRAM_BONUS = 0.5
HEADING_BONUS = 0.3
IDENTIFIER_BONUS = 1.0


class Reranker(Protocol):
    name: str

    async def score(self, query: str, hits: Sequence[Hit]) -> list[float]: ...


def _rerank_text(hit: Hit) -> str:
    return f"{hit.heading}\n{hit.text}" if hit.heading else hit.text


def lexical_scores(query: str, passages: Sequence[str], headings: Sequence[str]) -> list[float]:
    if not passages:
        return []
    query_terms = list(dict.fromkeys(content_terms(query)))
    query_set = set(query_terms)
    query_bigrams = set(pairwise(content_terms(query)))
    query_ids = [
        re.compile(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])") for token in identifiers(query)
    ]
    documents = [content_terms(passage) for passage in passages]
    count = len(documents)
    average = sum(len(d) for d in documents) / count or 1.0
    frequency = Counter(term for document in documents for term in set(document))
    idf = {
        term: math.log(1 + (count - frequency[term] + 0.5) / (frequency[term] + 0.5))
        for term in query_terms
    }
    raw: list[float] = []
    for document, passage, heading in zip(documents, passages, headings, strict=True):
        tf = Counter(document)
        length = len(document) or 1
        bm25 = sum(
            idf[term]
            * tf[term]
            * (BM25_K1 + 1)
            / (tf[term] + BM25_K1 * (1 - BM25_B + BM25_B * length / average))
            for term in query_terms
            if tf[term]
        )
        bigrams = len(query_bigrams & set(pairwise(document)))
        heading_share = (
            len(query_set & set(content_terms(heading))) / len(query_set) if query_set else 0.0
        )
        lowered = passage.lower()
        exact = any(pattern.search(lowered) for pattern in query_ids)
        raw.append(
            bm25
            + BIGRAM_BONUS * bigrams
            + HEADING_BONUS * heading_share
            + (IDENTIFIER_BONUS if exact else 0.0)
        )
    top = max(raw)
    return [value / top if top > 0 else 0.0 for value in raw]


class LexicalReranker:
    name = "lexical"

    async def score(self, query: str, hits: Sequence[Hit]) -> list[float]:
        return lexical_scores(query, [h.text for h in hits], [h.heading for h in hits])


class CrossEncoderReranker:
    """fastembed's TextCrossEncoder in a worker thread; the model loads once per process."""

    name = "cross-encoder"

    def __init__(self, model: str, cache_dir: Path | None) -> None:
        self.model_name = model
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._model: Any = None
        self._lock = asyncio.Lock()

    async def load(self) -> Any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    self._model = await anyio.to_thread.run_sync(
                        lambda: TextCrossEncoder(self.model_name, cache_dir=self._cache_dir)
                    )
                    log.info("reranker_loaded", model=self.model_name)
        return self._model

    async def score(self, query: str, hits: Sequence[Hit]) -> list[float]:
        if not hits:
            return []
        model = await self.load()
        passages = [_rerank_text(hit) for hit in hits]
        logits = await anyio.to_thread.run_sync(
            lambda: list(model.rerank(query, passages, batch_size=32))
        )
        return [1.0 / (1.0 + math.exp(-float(value))) for value in logits]


class RerankerPool:
    """The rerankers of one process. A cross-encoder that fails to load is remembered, so
    every later request goes straight to the lexical fallback instead of retrying the load."""

    def __init__(self, model: str, cache_dir: Path | None) -> None:
        self.lexical = LexicalReranker()
        self.cross_encoder = CrossEncoderReranker(model, cache_dir)
        self._cross_encoder_error: str | None = None

    @property
    def cross_encoder_error(self) -> str | None:
        return self._cross_encoder_error

    async def rerank(self, kind: str, query: str, hits: list[Hit]) -> tuple[list[Hit], bool]:
        """Hits reordered by the reranker, and whether the lexical fallback answered."""
        if kind == "none" or not hits:
            return hits, False
        fallback = False
        if kind == "cross-encoder" and self._cross_encoder_error is None:
            try:
                scores = await self.cross_encoder.score(query, hits)
            except Exception as exc:
                self._cross_encoder_error = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("cross_encoder_unavailable", error=self._cross_encoder_error)
                scores = await self.lexical.score(query, hits)
                fallback = True
        elif kind == "cross-encoder":
            scores = await self.lexical.score(query, hits)
            fallback = True
        else:
            scores = await self.lexical.score(query, hits)
        if fallback:
            metrics.RERANK_FALLBACKS.inc()
        for hit, value in zip(hits, scores, strict=True):
            hit.rerank_score = value
        ordered = sorted(hits, key=lambda h: (-(h.rerank_score or 0.0), -h.fused_score))
        for rank, hit in enumerate(ordered, start=1):
            hit.rerank_rank = rank
        return ordered, fallback

    async def warm_up(self) -> None:
        try:
            await self.cross_encoder.load()
        except Exception as exc:
            self._cross_encoder_error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("cross_encoder_unavailable", error=self._cross_encoder_error)
