"""Serving: retrieval over a pipeline version's index, and cited answers.

The plan resolves the version (active unless named), its index and embedding model, and the
retrieval settings with the request's overrides applied. Retrieval then runs the candidate
searches the mode asks for, fuses them, reranks the head of the list and returns the top k
with every stage's score and rank. Evaluation runs call `retrieve` directly, without the
result cache and without query logging.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import orjson
from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.ai.citations import extract_citations
from ragkit_server.ai.embeddings import EmbeddingSpec, spec_for_index
from ragkit_server.core import metrics
from ragkit_server.core.errors import NotFoundError
from ragkit_server.core.logging import get_logger
from ragkit_server.models import Chunk, Collection, Index, PipelineVersion, Project
from ragkit_server.models.enums import QueryKind
from ragkit_server.repositories.chunks import ChunkRepository
from ragkit_server.repositories.pipelines import PipelineRepository
from ragkit_server.repositories.query_logs import QueryLogRepository
from ragkit_server.retrieval.filters import compile_filter
from ragkit_server.retrieval.fusion import ranked, reciprocal_rank_fusion, weighted_fusion
from ragkit_server.retrieval.keyword import keyword_query
from ragkit_server.retrieval.packing import pack_context
from ragkit_server.retrieval.types import Hit
from ragkit_server.schemas.pipeline import (
    AnswerConfig,
    AnswerOverrides,
    PipelineConfig,
    RetrievalConfig,
    RetrievalOverrides,
    apply_answer,
    apply_retrieval,
)
from ragkit_server.schemas.retrieval import (
    AnswerRequest,
    AnswerResponse,
    QueryRequest,
    QueryResponse,
)
from ragkit_server.services.container import Container
from ragkit_server.services.pipelines import PipelineService
from ragkit_server.services.principal import Principal

log = get_logger("ragkit.retrieval")
_OVERRIDE_FIELDS = tuple(RetrievalOverrides.model_fields)
_ANSWER_FIELDS = tuple(AnswerOverrides.model_fields)


@dataclass(slots=True)
class Plan:
    collection: Collection
    version: PipelineVersion
    index: Index
    config: PipelineConfig
    retrieval: RetrievalConfig
    spec: EmbeddingSpec


@dataclass(slots=True)
class Outcome:
    hits: list[Hit]
    candidates: dict[str, int]
    timings: dict[str, float] = field(default_factory=dict)
    rerank_fallback: bool = False
    index_status: str = "ready"


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def query_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


class RetrievalService:
    def __init__(self, container: Container, session: AsyncSession) -> None:
        self.c = container
        self.session = session
        self.chunks = ChunkRepository(session)
        self.pipelines = PipelineRepository(session)

    async def plan(
        self,
        collection: Collection,
        number: int | None,
        overrides: RetrievalOverrides | None = None,
        version: PipelineVersion | None = None,
    ) -> Plan:
        version = version or await PipelineService(self.c, self.session).version(collection, number)
        index = await self.pipelines.index(version.index_id)
        if index is None:
            raise NotFoundError("The index of this pipeline version is missing.")
        config = PipelineConfig.model_validate(version.config)
        return Plan(
            collection=collection,
            version=version,
            index=index,
            config=config,
            retrieval=apply_retrieval(config.retrieval, overrides),
            spec=spec_for_index(index.embedding_model, index.config, index.embedding_dim),
        )

    async def retrieve(
        self,
        plan: Plan,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        document_ids: Sequence[uuid.UUID] | None = None,
    ) -> Outcome:
        settings = plan.retrieval
        compiled = compile_filter(filters, Chunk.meta)
        started = time.perf_counter()
        timings: dict[str, float] = {}
        vector: list[tuple[uuid.UUID, float]] = []
        keyword: list[tuple[uuid.UUID, float]] = []
        if settings.mode in ("vector", "hybrid"):
            step = time.perf_counter()
            query_vector = await self.c.embedders.get(plan.spec).embed_query(query)
            timings["embed"] = _ms(step)
            step = time.perf_counter()
            vector = await self.chunks.vector_candidates(
                index_id=plan.index.id,
                dim=plan.index.embedding_dim,
                query=query_vector,
                filters=compiled,
                document_ids=document_ids,
                limit=settings.candidates,
            )
            timings["vector"] = _ms(step)
        if settings.mode in ("keyword", "hybrid"):
            step = time.perf_counter()
            tsquery = keyword_query(query)
            if tsquery is not None:
                keyword = await self.chunks.keyword_candidates(
                    index_id=plan.index.id,
                    tsquery=tsquery,
                    filters=compiled,
                    document_ids=document_ids,
                    limit=settings.candidates,
                )
            timings["keyword"] = _ms(step)

        step = time.perf_counter()
        vector_scores, keyword_scores = dict(vector), dict(keyword)
        if settings.mode == "hybrid" and settings.fusion == "weighted":
            fused = weighted_fusion(
                vector_scores, keyword_scores, vector_weight=settings.vector_weight
            )
        elif settings.mode == "hybrid":
            fused = reciprocal_rank_fusion(
                [i for i, _ in vector],
                [i for i, _ in keyword],
                k=settings.rrf_k,
                vector_weight=settings.vector_weight,
            )
        else:
            fused = vector_scores or keyword_scores
        order = ranked(fused)[: settings.candidates]
        timings["fusion"] = _ms(step)

        rows = await self.chunks.hydrate(plan.index.id, order)
        vector_rank = {item: rank for rank, (item, _) in enumerate(vector, start=1)}
        keyword_rank = {item: rank for rank, (item, _) in enumerate(keyword, start=1)}
        hits = [
            Hit(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.document_title,
                external_id=row.external_id,
                location=row.location,
                heading=row.heading,
                text=row.text,
                context=row.context,
                token_count=row.token_count,
                metadata=row.metadata,
                section_ordinal=row.section_ordinal,
                vector_score=vector_scores.get(row.id),
                keyword_score=keyword_scores.get(row.id),
                fused_score=fused[row.id],
                vector_rank=vector_rank.get(row.id),
                keyword_rank=keyword_rank.get(row.id),
                fused_rank=position,
            )
            for position, chunk_id in enumerate(order, start=1)
            if (row := rows.get(chunk_id)) is not None
        ]

        fallback = False
        if settings.rerank != "none" and hits:
            step = time.perf_counter()
            head, tail = hits[: settings.rerank_candidates], hits[settings.rerank_candidates :]
            head, fallback = await self.c.rerankers.rerank(settings.rerank, query, head)
            hits = head + tail
            timings["rerank"] = _ms(step)
        timings["total"] = _ms(started)
        for stage, value in timings.items():
            metrics.RETRIEVAL_STAGE.labels(stage).observe(value / 1000)
        progress = await self.pipelines.progress([plan.index.id])
        return Outcome(
            hits=hits[: settings.top_k],
            candidates={"vector": len(vector), "keyword": len(keyword), "fused": len(order)},
            timings=timings,
            rerank_fallback=fallback,
            index_status=progress[plan.index.id].status.value,
        )

    # Serving ----------------------------------------------------------------------------

    @staticmethod
    def _overrides(request: QueryRequest) -> RetrievalOverrides:
        return RetrievalOverrides.model_validate(
            {name: getattr(request, name) for name in _OVERRIDE_FIELDS}
        )

    def _response(
        self, request: QueryRequest, plan: Plan, outcome: Outcome, *, cached: bool
    ) -> QueryResponse:
        settings = plan.retrieval
        return QueryResponse.model_validate(
            {
                "query": request.query,
                "pipeline_version": plan.version.version,
                "index_id": plan.index.id,
                "index_status": outcome.index_status,
                "mode": settings.mode,
                "fusion": settings.fusion if settings.mode == "hybrid" else None,
                "rerank": {"kind": settings.rerank, "fallback": outcome.rerank_fallback},
                "hits": [hit.public(rank=i) for i, hit in enumerate(outcome.hits, start=1)],
                "candidates": outcome.candidates,
                "timings_ms": outcome.timings,
                "cached": cached,
            }
        )

    def _cache_key(self, request: QueryRequest, plan: Plan) -> str:
        material = orjson.dumps(
            {
                "query": request.query,
                "version": str(plan.version.id),
                "retrieval": plan.retrieval.model_dump(),
                "filters": request.filters,
                "documents": sorted(str(d) for d in request.document_ids or []),
            },
            option=orjson.OPT_SORT_KEYS,
        )
        digest = hashlib.sha256(material).hexdigest()
        return f"q:{plan.collection.id}:{plan.collection.corpus_version}:{digest}"

    async def query(
        self, project: Project, collection: Collection, request: QueryRequest, principal: Principal
    ) -> QueryResponse:
        started = time.perf_counter()
        plan = await self.plan(collection, request.pipeline_version, self._overrides(request))
        ttl = self.c.settings.query_cache_ttl_s
        key = self._cache_key(request, plan) if request.use_cache and ttl else None
        if key is not None:
            try:
                stored = await self.c.redis.get(key)
            except Exception:
                stored = None
            if stored is not None:
                metrics.CACHE.labels("query", "hit").inc()
                response = QueryResponse.model_validate_json(stored)
                response.cached = True
                response.timings_ms = {"total": _ms(started)}
                await self._log(project, collection, plan, request.query, principal, response)
                return response
            metrics.CACHE.labels("query", "miss").inc()
        outcome = await self.retrieve(
            plan, request.query, filters=request.filters, document_ids=request.document_ids
        )
        response = self._response(request, plan, outcome, cached=False)
        if key is not None:
            try:
                await self.c.redis.set(key, response.model_dump_json(), ex=ttl)
            except Exception:
                log.warning("query_cache_write_failed")
        metrics.QUERIES.labels("query", plan.retrieval.mode).inc()
        await self._log(project, collection, plan, request.query, principal, response)
        return response

    async def answer(
        self,
        project: Project,
        collection: Collection,
        request: AnswerRequest,
        principal: Principal,
    ) -> AnswerResponse:
        started = time.perf_counter()
        plan = await self.plan(collection, request.pipeline_version, self._overrides(request))
        answer_settings = apply_answer(
            plan.config.answer,
            AnswerOverrides.model_validate(
                {name: getattr(request, name) for name in _ANSWER_FIELDS}
            ),
        )
        self.c.answerers.check(answer_settings.answerer)
        outcome = await self.retrieve(
            plan, request.query, filters=request.filters, document_ids=request.document_ids
        )
        retrieval = self._response(request, plan, outcome, cached=False)
        text, citations, sources, usage, label, answer_ms = await self.compose(
            plan, request.query, outcome.hits, answer_settings
        )
        metrics.QUERIES.labels("answer", plan.retrieval.mode).inc()
        response = AnswerResponse.model_validate(
            {
                "query": request.query,
                "answer": text,
                "answerer": label,
                "citations": citations,
                "sources": [hit.public(rank=hit.n) for hit in sources],
                "usage": usage,
                "retrieval": retrieval,
                "timings_ms": {
                    "retrieval": outcome.timings.get("total", 0.0),
                    "answer": answer_ms,
                    "total": _ms(started),
                },
            }
        )
        await self._log(
            project, collection, plan, request.query, principal, retrieval, answerer=label
        )
        return response

    async def compose(
        self, plan: Plan, question: str, hits: list[Hit], settings: AnswerConfig
    ) -> tuple[str, list[dict[str, Any]], list[Hit], dict[str, int], str, float]:
        """Pack the hits, run the answerer, verify the citations."""
        step = time.perf_counter()
        sources = pack_context(
            hits, self.c.tokens, budget=settings.context_tokens, max_sources=settings.max_sources
        )
        draft = await self.c.answerers.answer(
            settings.answerer,
            question,
            sources,
            model=settings.model,
            embedder=self.c.embedders.get(plan.spec),
        )
        text, citations = extract_citations(draft.text, sources)
        elapsed = _ms(step)
        metrics.ANSWER_DURATION.labels(settings.answerer).observe(elapsed / 1000)
        usage = {
            "prompt_tokens": draft.usage.prompt_tokens,
            "completion_tokens": draft.usage.completion_tokens,
        }
        return text, citations, sources, usage, draft.answerer, elapsed

    async def _log(
        self,
        project: Project,
        collection: Collection,
        plan: Plan,
        query: str,
        principal: Principal,
        response: QueryResponse,
        *,
        answerer: str | None = None,
    ) -> None:
        """One analytics row per served request; a failure here never fails the request."""
        try:
            await QueryLogRepository(self.session).add(
                [
                    {
                        "project_id": project.id,
                        "collection_id": collection.id,
                        "pipeline_version": plan.version.version,
                        "kind": QueryKind.ANSWER if answerer else QueryKind.QUERY,
                        "mode": plan.retrieval.mode,
                        "rerank": plan.retrieval.rerank,
                        "top_k": plan.retrieval.top_k,
                        "hit_count": len(response.hits),
                        "top_score": response.hits[0].score if response.hits else None,
                        "latency_ms": int(response.timings_ms.get("total", 0.0)),
                        "cached": response.cached,
                        "answerer": answerer,
                        "query_hash": query_hash(query),
                        "query_text": query[:500] if self.c.settings.query_log_text else None,
                        "user_id": principal.user_id,
                        "api_key_id": principal.api_key_id,
                    }
                ]
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            log.warning("query_log_failed")
