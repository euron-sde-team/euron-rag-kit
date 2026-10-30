"""Evaluation: datasets, runs (experiments), their execution, comparison and the CI gate.

A run snapshots everything that determines its result (the version's configuration with the
run's overrides applied, k, the grader, whether answers are generated), so it stays
reproducible after the dataset or the collection changes. Execution answers every question
with exactly that configuration, without the result cache, and stores per-question results;
a retried run resumes after the questions it already finished.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ragkit_server.ai.judge import JudgeError
from ragkit_server.core import metrics as prometheus
from ragkit_server.core.errors import AppError, ConflictError, NotFoundError, UnprocessableError
from ragkit_server.core.logging import get_logger
from ragkit_server.evaluation.aggregate import ResultRow, aggregate
from ragkit_server.evaluation.compare import ItemView, RunView, compare
from ragkit_server.evaluation.gate import expand_drop, run_gate
from ragkit_server.evaluation.metrics import (
    answer_correctness,
    answer_relevance,
    faithfulness,
    retrieval_metrics,
    strip_citations,
)
from ragkit_server.evaluation.relevance import ExpectedSource, RetrievedChunk, judge
from ragkit_server.ingestion.sniff import slugify
from ragkit_server.integrations.queue import Job
from ragkit_server.models import Collection, Dataset, DatasetItem, EvalResult, EvalRun, Project
from ragkit_server.models.enums import RunStatus
from ragkit_server.repositories.collections import CollectionRepository
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.repositories.evaluation import EvaluationRepository
from ragkit_server.repositories.pipelines import PipelineRepository
from ragkit_server.schemas.common import Page
from ragkit_server.schemas.evaluation import (
    ComparisonOut,
    DatasetCreate,
    DatasetOut,
    DatasetUpdate,
    GateOut,
    GateRequest,
    ItemIn,
    ItemsImport,
    ResultOut,
    RunCreate,
    RunOut,
)
from ragkit_server.schemas.pipeline import (
    AnswerConfig,
    PipelineConfig,
    RetrievalOverrides,
    apply_answer,
    apply_retrieval,
)
from ragkit_server.services import audit
from ragkit_server.services.container import Container
from ragkit_server.services.pipelines import PipelineService
from ragkit_server.services.principal import Principal
from ragkit_server.services.retrieval import Plan, RetrievalService

log = get_logger("ragkit.evaluation")
PASSAGE_PREVIEW = 700


def default_label(version: int, config: PipelineConfig) -> str:
    retrieval = config.retrieval
    label = f"v{version} {config.chunking.strategy.replace('_', ' ')}, {retrieval.mode}"
    if retrieval.mode == "hybrid" and retrieval.fusion == "weighted":
        label += " (weighted)"
    if retrieval.rerank != "none":
        label += f" + {retrieval.rerank}"
    return label


class EvaluationService:
    def __init__(self, container: Container, session: AsyncSession | None = None) -> None:
        self.c = container
        self._session = session

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("this operation needs a request session")
        return self._session

    @property
    def repo(self) -> EvaluationRepository:
        return EvaluationRepository(self.session)

    # Datasets ---------------------------------------------------------------------------

    async def dataset(self, project: Project, ref: str) -> Dataset:
        dataset = await self.repo.dataset(project.id, ref)
        if dataset is None:
            raise NotFoundError("Dataset not found.")
        return dataset

    async def datasets(self, project: Project) -> list[DatasetOut]:
        rows = await self.repo.datasets(project.id)
        latest = await self.repo.latest_runs([d.id for d, _, _ in rows])
        return [self._dataset_out(d, slug, count, latest.get(d.id)) for d, slug, count in rows]

    async def dataset_out(self, project: Project, dataset: Dataset) -> DatasetOut:
        collection = await CollectionRepository(self.session).get(
            project.id, str(dataset.collection_id)
        )
        latest = await self.repo.latest_runs([dataset.id])
        return self._dataset_out(
            dataset,
            collection.slug if collection else "",
            await self.repo.item_count(dataset.id),
            latest.get(dataset.id),
        )

    @staticmethod
    def _dataset_out(
        dataset: Dataset, collection_slug: str, item_count: int, last_run: EvalRun | None
    ) -> DatasetOut:
        return DatasetOut(
            id=dataset.id,
            slug=dataset.slug,
            name=dataset.name,
            description=dataset.description,
            collection_id=dataset.collection_id,
            collection_slug=collection_slug,
            item_count=item_count,
            gate=dataset.gate,
            baseline_run_id=dataset.baseline_run_id,
            last_run=(
                {
                    "id": str(last_run.id),
                    "label": last_run.label,
                    "status": last_run.status,
                    "created_at": last_run.created_at.isoformat(),
                    "means": (last_run.metrics or {}).get("means", {}),
                }
                if last_run
                else None
            ),
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    async def _check_sources(self, collection_id: uuid.UUID, items: list[ItemIn]) -> None:
        """Every expected document must exist: a typo would silently zero every metric."""
        wanted = {source.document for item in items for source in item.expected_sources}
        known = await DocumentRepository(self.session).external_ids(collection_id, sorted(wanted))
        unknown = sorted(wanted - known)
        if unknown:
            raise UnprocessableError(
                f"Unknown document external id(s): {', '.join(unknown[:10])}.",
                code="unknown_documents",
                details={"unknown": unknown},
            )

    @staticmethod
    def _item_rows(items: list[ItemIn]) -> list[dict[str, Any]]:
        return [
            {
                "question": item.question.strip(),
                "expected_sources": [s.model_dump() for s in item.expected_sources],
                "expected_answer": item.expected_answer,
                "tags": item.tags,
            }
            for item in items
        ]

    async def create_dataset(
        self, project: Project, principal: Principal, body: DatasetCreate
    ) -> Dataset:
        collection = await CollectionRepository(self.session).get(project.id, body.collection)
        if collection is None:
            raise NotFoundError("Collection not found.")
        slug = body.slug or slugify(body.name, limit=48, fallback="dataset")
        if await self.repo.slug_taken(project.id, slug):
            raise ConflictError("A dataset with that slug already exists.")
        await self._check_sources(collection.id, body.items)
        dataset = await self.repo.add_dataset(
            Dataset(
                project_id=project.id,
                collection_id=collection.id,
                slug=slug,
                name=body.name.strip(),
                description=body.description.strip(),
                gate=body.gate.model_dump(),
                created_by=principal.user_id,
            )
        )
        await self.repo.add_items(dataset.id, self._item_rows(body.items))
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="dataset.created",
            target_type="dataset",
            target_id=dataset.id,
            details={"slug": slug, "items": len(body.items)},
        )
        await self.session.commit()
        return dataset

    async def update_dataset(
        self, project: Project, dataset: Dataset, principal: Principal, body: DatasetUpdate
    ) -> Dataset:
        if body.name is not None:
            dataset.name = body.name.strip()
        if body.description is not None:
            dataset.description = body.description.strip()
        if body.gate is not None:
            dataset.gate = body.gate.model_dump()
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="dataset.updated",
            target_type="dataset",
            target_id=dataset.id,
            details={"fields": sorted(body.model_dump(exclude_none=True))},
        )
        await self.session.commit()
        return dataset

    async def delete_dataset(
        self, project: Project, dataset: Dataset, principal: Principal
    ) -> None:
        await self.session.delete(dataset)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="dataset.deleted",
            target_type="dataset",
            target_id=dataset.id,
            details={"slug": dataset.slug},
        )
        await self.session.commit()

    async def items(
        self, dataset: Dataset, *, limit: int, offset: int
    ) -> tuple[list[DatasetItem], int]:
        return (
            await self.repo.items(dataset.id, limit=limit, offset=offset),
            await self.repo.item_count(dataset.id),
        )

    async def import_items(
        self, project: Project, dataset: Dataset, principal: Principal, body: ItemsImport
    ) -> int:
        await self._check_sources(dataset.collection_id, body.items)
        if body.replace:
            await self.repo.clear_items(dataset.id)
        await self.repo.add_items(dataset.id, self._item_rows(body.items))
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="dataset.items_imported",
            target_type="dataset",
            target_id=dataset.id,
            details={"items": len(body.items), "replace": body.replace},
        )
        await self.session.commit()
        return await self.repo.item_count(dataset.id)

    async def delete_item(
        self, project: Project, dataset: Dataset, principal: Principal, item_id: uuid.UUID
    ) -> None:
        item = await self.repo.item(dataset.id, item_id)
        if item is None:
            raise NotFoundError("Question not found.")
        await self.session.delete(item)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="dataset.item_deleted",
            target_type="dataset",
            target_id=dataset.id,
        )
        await self.session.commit()

    # Runs -------------------------------------------------------------------------------

    async def run(self, project: Project, run_id: uuid.UUID) -> EvalRun:
        run = await self.repo.run(project.id, run_id)
        if run is None:
            raise NotFoundError("Evaluation run not found.")
        return run

    async def create_run(self, project: Project, principal: Principal, body: RunCreate) -> EvalRun:
        dataset = await self.dataset(project, body.dataset)
        collection = await CollectionRepository(self.session).get(
            project.id, str(dataset.collection_id)
        )
        if collection is None:
            raise NotFoundError("Collection not found.")
        version = await PipelineService(self.c, self.session).version(
            collection, body.pipeline_version
        )
        total = await self.repo.item_count(dataset.id)
        if total == 0:
            raise UnprocessableError("This dataset has no questions yet.", code="empty_dataset")
        config = PipelineConfig.model_validate(version.config)
        retrieval = apply_retrieval(config.retrieval, body.retrieval)
        retrieval = retrieval.model_copy(
            update={"top_k": body.k, "candidates": max(retrieval.candidates, body.k)}
        )
        answer = apply_answer(config.answer, body.answer)
        if body.answers:
            self.c.answerers.check(answer.answerer)
        if body.grader == "model" and self.c.judge is None:
            raise UnprocessableError(
                "Model grading needs LLM_PROVIDER and LLM_MODEL (or JUDGE_MODEL) configured.",
                code="provider_unavailable",
            )
        effective = config.model_copy(update={"retrieval": retrieval, "answer": answer})
        snapshot = {
            **effective.model_dump(),
            # Only the chunking fields the strategy uses, so comparisons show real differences.
            "chunking": effective.chunking.index_fields(),
            "evaluation": {"k": body.k, "grader": body.grader, "answers": body.answers},
        }
        run = await self.repo.add_run(
            EvalRun(
                project_id=project.id,
                dataset_id=dataset.id,
                collection_id=collection.id,
                pipeline_version_id=version.id,
                label=(body.label or default_label(version.version, effective))[:160],
                status=RunStatus.QUEUED,
                config=snapshot,
                k=body.k,
                grader=body.grader,
                total_items=total,
                created_by=principal.user_id,
            )
        )
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="eval_run.created",
            target_type="eval_run",
            target_id=run.id,
            details={"dataset": dataset.slug, "version": version.version, "label": run.label},
        )
        await self.session.commit()
        await self.c.queue.enqueue(Job.evaluate(project.id, run.id))
        return run

    async def runs_out(self, runs: list[EvalRun]) -> list[RunOut]:
        datasets, collections, versions = await self.repo.run_context(runs)
        out = []
        for run in runs:
            dataset = datasets.get(run.dataset_id)
            collection = collections.get(run.collection_id)
            duration = (
                int((run.finished_at - run.started_at).total_seconds() * 1000)
                if run.finished_at and run.started_at
                else None
            )
            out.append(
                RunOut(
                    id=run.id,
                    label=run.label,
                    status=run.status,
                    dataset={
                        "id": str(run.dataset_id),
                        "slug": dataset.slug if dataset else "",
                        "name": dataset.name if dataset else "",
                    },
                    collection={
                        "id": str(run.collection_id),
                        "slug": collection.slug if collection else "",
                        "name": collection.name if collection else "",
                    },
                    pipeline_version=versions.get(run.pipeline_version_id, 0),
                    k=run.k,
                    grader=run.grader,
                    config=run.config,
                    total_items=run.total_items,
                    completed_items=run.completed_items,
                    metrics=run.metrics,
                    error=run.error,
                    is_baseline=bool(dataset and dataset.baseline_run_id == run.id),
                    created_at=run.created_at,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    duration_ms=duration,
                )
            )
        return out

    async def list_runs(
        self,
        project: Project,
        *,
        dataset: str | None,
        collection: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> Page[RunOut]:
        dataset_id = (await self.dataset(project, dataset)).id if dataset else None
        collection_id = None
        if collection:
            found = await CollectionRepository(self.session).get(project.id, collection)
            if found is None:
                raise NotFoundError("Collection not found.")
            collection_id = found.id
        runs, total = await self.repo.runs(
            project.id,
            dataset_id=dataset_id,
            collection_id=collection_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return Page[RunOut](
            items=await self.runs_out(runs), total=total, limit=limit, offset=offset
        )

    async def results(self, run: EvalRun, *, limit: int, offset: int) -> Page[ResultOut]:
        results = await self.repo.results(run.id, limit=limit, offset=offset)
        items = await self.repo.items_by_ids([r.item_id for r in results if r.item_id])
        out = []
        for result in results:
            item = items.get(result.item_id) if result.item_id else None
            out.append(
                ResultOut(
                    id=result.id,
                    item_id=result.item_id,
                    ordinal=result.ordinal,
                    question=result.question,
                    tags=result.tags,
                    retrieved=result.retrieved,
                    answer=result.answer,
                    citations=result.citations,
                    metrics=result.metrics,
                    grading=result.grading,
                    expected_sources=item.expected_sources if item else [],
                    expected_answer=item.expected_answer if item else None,
                    latency_ms=result.latency_ms,
                    retrieval_ms=result.retrieval_ms,
                    answer_ms=result.answer_ms,
                    error=result.error,
                )
            )
        return Page[ResultOut](
            items=out, total=await self.repo.result_count(run.id), limit=limit, offset=offset
        )

    async def delete_run(self, project: Project, run: EvalRun, principal: Principal) -> None:
        if run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            raise ConflictError("Wait for the run to finish before deleting it.")
        await self.session.delete(run)
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="eval_run.deleted",
            target_type="eval_run",
            target_id=run.id,
        )
        await self.session.commit()

    async def set_baseline(self, project: Project, run: EvalRun, principal: Principal) -> EvalRun:
        if run.status != RunStatus.COMPLETED:
            raise ConflictError("Only a completed run can be a baseline.")
        dataset = await self.repo.dataset_by_id(run.dataset_id)
        if dataset is None:
            raise NotFoundError("Dataset not found.")
        dataset.baseline_run_id = run.id
        await audit.record(
            self.session,
            project_id=project.id,
            principal=principal,
            action="eval_run.baseline_set",
            target_type="eval_run",
            target_id=run.id,
            details={"dataset": dataset.slug},
        )
        await self.session.commit()
        return run

    async def compare(self, project: Project, run_ids: list[uuid.UUID]) -> ComparisonOut:
        if not 2 <= len(run_ids) <= 4:
            raise UnprocessableError("Compare two to four runs.")
        runs = await self.repo.runs_by_ids(project.id, run_ids)
        if len(runs) != len(set(run_ids)):
            raise NotFoundError("Evaluation run not found.")
        views = [
            RunView(
                id=str(run.id),
                label=run.label,
                dataset_id=str(run.dataset_id),
                means=(run.metrics or {}).get("means", {}),
                config=run.config,
            )
            for run in runs
        ]
        items: dict[str, list[ItemView]] = {}
        for run in runs:
            items[str(run.id)] = [
                ItemView(
                    key=str(result.item_id or result.ordinal),
                    question=result.question,
                    metrics=result.metrics,
                    tags=result.tags,
                    top_documents=[r["external_id"] for r in result.retrieved[:3]],
                )
                for result in await self.repo.results(run.id)
            ]
        compared = compare(views, items)
        return ComparisonOut(runs=await self.runs_out(runs), **compared)

    async def gate(self, project: Project, run: EvalRun, body: GateRequest) -> GateOut:
        dataset = await self.repo.dataset_by_id(run.dataset_id)
        settings = dataset.gate if dataset else {}
        baseline_id = body.baseline_run_id or (dataset.baseline_run_id if dataset else None)
        if run.status != RunStatus.COMPLETED:
            return GateOut(
                passed=False,
                run_id=run.id,
                run_status=run.status,
                baseline_run_id=baseline_id,
                checks=[],
            )
        baseline = await self.repo.run(project.id, baseline_id) if baseline_id else None
        if baseline_id and baseline is None:
            raise NotFoundError("Baseline run not found.")
        candidate = (run.metrics or {}).get("means", {})
        reference = (
            (baseline.metrics or {}).get("means", {})
            if baseline is not None and baseline.status == RunStatus.COMPLETED
            else None
        )
        minimums = body.min if body.min is not None else settings.get("min", {})
        drops = expand_drop(
            body.max_drop if body.max_drop is not None else settings.get("max_drop"), candidate
        )
        passed, checks = run_gate(candidate, reference, minimums=minimums, max_drop=drops)
        return GateOut.model_validate(
            {
                "passed": passed,
                "run_id": run.id,
                "run_status": run.status,
                "baseline_run_id": baseline.id if baseline else None,
                "checks": [check.as_dict() for check in checks],
            }
        )

    # Execution (worker) -----------------------------------------------------------------

    async def execute(self, run_id: uuid.UUID, *, final_attempt: bool = True) -> bool:
        """Run (or resume) an evaluation. Returns False when the job should be retried."""
        async with self.c.db.session() as session:
            repo = EvaluationRepository(session)
            run = await repo.run_for_update(run_id)
            if run is None or RunStatus(run.status).finished:
                return True
            run.status = RunStatus.RUNNING
            run.attempts += 1
            run.error = None
            run.started_at = run.started_at or datetime.now(UTC)
            dataset_id, collection_id, version_id = (
                run.dataset_id,
                run.collection_id,
                run.pipeline_version_id,
            )
            config, k, grader = dict(run.config), run.k, run.grader
            await session.commit()

        started = time.perf_counter()
        try:
            async with self.c.db.session() as session:
                repo = EvaluationRepository(session)
                collection = await session.get(Collection, collection_id)
                version = await PipelineRepository(session).version_by_id(version_id)
                if collection is None or version is None:
                    raise UnprocessableError("The collection or pipeline version was deleted.")
                retrieval = RetrievalService(self.c, session)
                plan = await retrieval.plan(
                    collection,
                    None,
                    RetrievalOverrides.model_validate(config["retrieval"]),
                    version=version,
                )
                answer = AnswerConfig.model_validate(config["answer"])
                answers = bool(config.get("evaluation", {}).get("answers", True))
                items = await repo.items(dataset_id)
                done = await repo.done_item_ids(run_id)
                for item in items:
                    if item.id in done:
                        continue
                    row = await self._evaluate(retrieval, plan, item, k, grader, answers, answer)
                    await repo.upsert_result({"run_id": run_id, **row})
                    done.add(item.id)
                    await repo.mark_run(run_id, completed_items=len(done), total_items=len(items))
                    await session.commit()
                results = await repo.results(run_id)
                summary = aggregate([_row(result) for result in results])
                await repo.mark_run(
                    run_id,
                    status=RunStatus.COMPLETED,
                    metrics=summary,
                    completed_items=len(results),
                    finished_at=datetime.now(UTC),
                )
                await session.commit()
        except Exception as exc:
            log.exception("eval_run_failed", run_id=str(run_id))
            message = exc.message if isinstance(exc, AppError) else "The run failed unexpectedly."
            async with self.c.db.session() as session:
                repo = EvaluationRepository(session)
                if final_attempt or isinstance(exc, AppError):
                    await repo.mark_run(
                        run_id,
                        status=RunStatus.FAILED,
                        error=message[:1000],
                        finished_at=datetime.now(UTC),
                    )
                    await session.commit()
                    prometheus.EVAL_RUNS.labels("failed").inc()
                    return True
                await repo.mark_run(run_id, status=RunStatus.QUEUED)
                await session.commit()
            return False
        prometheus.EVAL_RUNS.labels("completed").inc()
        log.info(
            "eval_run_completed",
            run_id=str(run_id),
            questions=len(results),
            seconds=round(time.perf_counter() - started, 1),
        )
        return True

    async def _evaluate(
        self,
        retrieval: RetrievalService,
        plan: Plan,
        item: DatasetItem,
        k: int,
        grader: str,
        answers: bool,
        answer: AnswerConfig,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        row: dict[str, Any] = {
            "item_id": item.id,
            "ordinal": item.ordinal,
            "question": item.question,
            "tags": list(item.tags or []),
        }
        try:
            outcome = await retrieval.retrieve(plan, item.question)
        except AppError as exc:
            return {
                **row,
                "error": exc.message,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        top = outcome.hits[:k]
        expected = [ExpectedSource(s["document"], s.get("evidence")) for s in item.expected_sources]
        judgement = judge([RetrievedChunk(h.external_id, h.passage) for h in top], expected)
        values: dict[str, float | None] = dict(retrieval_metrics(judgement, k)) if expected else {}
        row["retrieved"] = [
            {
                "rank": rank,
                "chunk_id": str(hit.chunk_id),
                "document_id": str(hit.document_id),
                "external_id": hit.external_id,
                "title": hit.document_title,
                "location": hit.location,
                "heading": hit.heading,
                "text": hit.passage[:PASSAGE_PREVIEW],
                "score": round(hit.score, 4),
                "relevant": bool(covers),
                "covers": sorted(covers),
            }
            for rank, (hit, covers) in enumerate(zip(top, judgement.covers, strict=True), start=1)
        ]
        row["retrieval_ms"] = int(outcome.timings.get("total", 0.0))
        if answers:
            text, citations, sources, _, label, answer_ms = await retrieval.compose(
                plan, item.question, outcome.hits, answer
            )
            contexts = [source.passage for source in sources]
            grading: dict[str, Any] = {"grader": "deterministic", "answerer": label}
            values["faithfulness"] = faithfulness(text, contexts)
            embedder = retrieval.embedder(plan)
            question_vector = await embedder.embed_query(item.question)
            answer_vector = (await embedder.embed_documents([strip_citations(text)]))[0]
            values["answer_relevance"] = answer_relevance(
                text, float(question_vector @ answer_vector)
            )
            if item.expected_answer:
                values["answer_correctness"] = answer_correctness(text, item.expected_answer)
            if grader == "model" and self.c.judge is not None:
                try:
                    verdict = await self.c.judge.grade(
                        item.question, text, contexts, item.expected_answer
                    )
                    values["faithfulness"] = verdict.faithfulness
                    if verdict.relevance is not None:
                        values["answer_relevance"] = verdict.relevance
                    if item.expected_answer and verdict.correctness is not None:
                        values["answer_correctness"] = verdict.correctness
                    grading.update({"grader": self.c.judge.label, "reason": verdict.reason})
                except (JudgeError, AppError) as exc:
                    grading.update({"grader_fallback": True, "reason": str(exc)[:300]})
            row.update(answer=text, citations=citations, grading=grading, answer_ms=int(answer_ms))
        row["metrics"] = {name: round(v, 4) for name, v in values.items() if v is not None}
        row["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return row


def _row(result: EvalResult) -> ResultRow:
    return ResultRow(
        metrics=result.metrics,
        tags=tuple(result.tags or ()),
        latency_ms=result.latency_ms,
        failed=result.error is not None,
    )
