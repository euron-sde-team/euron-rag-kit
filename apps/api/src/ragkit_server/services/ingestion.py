"""Parse and index jobs, run by the worker (SQS) or in the API process (inline queue).

- **parse**: load the original (from storage, or fetch the URL and keep a snapshot), parse
  it into sections, then queue one index job per index of the collection. A document is
  parsed once however many pipeline versions read it.
- **index**: clean, chunk and embed one document for one index, then swap its chunks in a
  single transaction, so readers never see a half-indexed document.

Both are idempotent: a duplicated message for finished work is a no-op, and a retry after a
crash redoes the work from the stored inputs.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import anyio
import numpy as np

from ragkit_server.ai.embeddings import spec_for_index
from ragkit_server.core import metrics
from ragkit_server.core.errors import AppError
from ragkit_server.core.logging import get_logger
from ragkit_server.core.text import normalize
from ragkit_server.ingestion.chunkers import chunk_sections
from ragkit_server.ingestion.cleaning import clean_sections
from ragkit_server.ingestion.parsers.registry import parse
from ragkit_server.ingestion.sniff import FILE_EXTENSIONS, MIME_TYPES, kind_for_response
from ragkit_server.ingestion.types import ParseError, ParseLimits
from ragkit_server.integrations.queue import Job
from ragkit_server.integrations.storage import document_key
from ragkit_server.models import Document
from ragkit_server.models.enums import DocumentKind, JobStatus, RunStatus, SourceType
from ragkit_server.repositories.chunks import ChunkRepository
from ragkit_server.repositories.collections import CollectionRepository
from ragkit_server.repositories.documents import DocumentRepository
from ragkit_server.repositories.evaluation import EvaluationRepository
from ragkit_server.repositories.pipelines import PipelineRepository
from ragkit_server.schemas.pipeline import PipelineConfig
from ragkit_server.services.container import Container
from ragkit_server.services.evaluation import EvaluationService
from ragkit_server.services.pipelines import chunking_options, cleaning_options, sections_from_rows

log = get_logger("ragkit.ingestion")
EMBED_BATCH = 64
MAX_ATTEMPTS = 3


class Outcome(StrEnum):
    DONE = "done"
    RETRY = "retry"


class IngestionService:
    def __init__(self, container: Container) -> None:
        self.c = container
        self.limits = ParseLimits(max_pages=container.settings.max_document_pages)

    async def handle(self, job: Job, *, final_attempt: bool = True) -> Outcome:
        if job.kind == "parse" and job.document_id is not None:
            return await self.parse(job.document_id, final_attempt=final_attempt)
        if job.kind == "index" and job.document_id is not None and job.index_id is not None:
            return await self.index(job.index_id, job.document_id, final_attempt=final_attempt)
        if job.kind == "eval" and job.run_id is not None:
            done = await EvaluationService(self.c).execute(job.run_id, final_attempt=final_attempt)
            return Outcome.DONE if done else Outcome.RETRY
        log.warning("job_ignored", kind=job.kind)
        return Outcome.DONE

    # Parsing ----------------------------------------------------------------------------

    async def parse(self, document_id: uuid.UUID, *, final_attempt: bool) -> Outcome:
        async with self.c.db.session() as session:
            document = await DocumentRepository(session).get_for_update(document_id)
            if document is None or document.status == JobStatus.READY:
                return Outcome.DONE
            document.status = JobStatus.PROCESSING
            document.attempts += 1
            document.error = None
            snapshot = _Snapshot.of(document)
            await session.commit()

        started = time.perf_counter()
        kind = snapshot.kind
        try:
            with anyio.fail_after(self.c.settings.job_timeout_s):
                if snapshot.source_type == SourceType.URL:
                    data, kind, fetched = await self._fetch(snapshot)
                else:
                    if snapshot.storage_key is None or kind is None:
                        raise ParseError("The original of this document is missing.")
                    data, fetched = await self.c.storage.get(snapshot.storage_key), {}
                parsed = await anyio.to_thread.run_sync(parse, kind, data, self.limits)
                rows: list[dict[str, Any]] = [
                    {
                        "ordinal": ordinal,
                        "kind": section.kind.value,
                        "label": section.label[:300],
                        "blocks": [
                            {"text": block.text, "level": block.heading_level}
                            for block in section.blocks
                        ],
                        "text": section.text,
                        "token_count": self.c.tokens.count(section.text),
                    }
                    for ordinal, section in enumerate(parsed.sections)
                ]
        except (ParseError, AppError) as exc:
            await self._fail_document(document_id, _message(exc), kind)
            return Outcome.DONE
        except TimeoutError:
            await self._fail_document(document_id, "Parsing took too long and was stopped.", kind)
            return Outcome.DONE
        except Exception:
            log.exception("parse_error", document_id=str(document_id))
            if final_attempt:
                await self._fail_document(document_id, "Parsing failed. Try reprocessing.", kind)
                return Outcome.DONE
            await self._requeue_document(document_id)
            return Outcome.RETRY

        async with self.c.db.session() as session:
            documents = DocumentRepository(session)
            pipelines = PipelineRepository(session)
            document = await documents.get_for_update(document_id)
            if document is None:
                return Outcome.DONE
            await documents.replace_sections(document.id, rows)
            for name, value in fetched.items():
                setattr(document, name, value)
            title = normalize(parsed.title or "")
            if (
                title
                and 3 <= len(title) <= 200
                and document.title
                in (
                    snapshot.default_title,
                    snapshot.source_uri,
                )
            ):
                document.title = title
            document.kind = kind.value if kind else None
            document.status = JobStatus.READY
            document.section_count = len(rows)
            document.token_count = sum(int(row["token_count"]) for row in rows)
            document.parsed_at = datetime.now(UTC)
            # A re-parse invalidates every index entry of the document; a first parse
            # creates them, one per index of the collection.
            requeued = set(await pipelines.requeue_document(document.id))
            fresh = [
                (index_id, document.id)
                for index_id in await pipelines.collection_index_ids(document.collection_id)
                if index_id not in requeued
            ]
            await pipelines.ensure_entries(document.project_id, fresh)
            jobs = [Job.index(document.project_id, i, document.id) for i in requeued] + [
                Job.index(document.project_id, i, d) for i, d in fresh
            ]
            await session.commit()
        for index_job in jobs:
            await self.c.queue.enqueue(index_job)
        metrics.DOCUMENTS_PARSED.labels(kind.value if kind else "unknown", "ready").inc()
        log.info(
            "parsed",
            document_id=str(document_id),
            sections=len(rows),
            seconds=round(time.perf_counter() - started, 2),
        )
        return Outcome.DONE

    async def _fetch(self, snapshot: _Snapshot) -> tuple[bytes, DocumentKind, dict[str, Any]]:
        if not snapshot.source_uri:
            raise ParseError("This URL source has no address.")
        page = await self.c.fetcher.fetch(snapshot.source_uri)
        if not page.data:
            raise ParseError("The page was empty.")
        kind = kind_for_response(page.content_type, page.url, page.data[:8192])
        key = document_key(
            snapshot.project_id, snapshot.collection_id, snapshot.id, FILE_EXTENSIONS[kind]
        )
        await self.c.storage.put(key, page.data, MIME_TYPES[kind])
        return (
            page.data,
            kind,
            {
                "storage_key": key,
                "mime_type": MIME_TYPES[kind],
                "size_bytes": len(page.data),
                "sha256": hashlib.sha256(page.data).hexdigest(),
            },
        )

    async def _fail_document(
        self, document_id: uuid.UUID, message: str, kind: DocumentKind | None
    ) -> None:
        metrics.DOCUMENTS_PARSED.labels(kind.value if kind else "unknown", "failed").inc()
        log.info("parse_failed", document_id=str(document_id), reason=message)
        async with self.c.db.session() as session:
            await DocumentRepository(session).mark(
                document_id, status=JobStatus.FAILED, error=message[:1000]
            )
            await session.commit()

    async def _requeue_document(self, document_id: uuid.UUID) -> None:
        async with self.c.db.session() as session:
            await DocumentRepository(session).mark(document_id, status=JobStatus.QUEUED)
            await session.commit()

    # Indexing ---------------------------------------------------------------------------

    async def index(
        self, index_id: uuid.UUID, document_id: uuid.UUID, *, final_attempt: bool
    ) -> Outcome:
        async with self.c.db.session() as session:
            pipelines = PipelineRepository(session)
            entry = await pipelines.entry_for_update(index_id, document_id)
            if entry is None or entry.status == JobStatus.READY:
                return Outcome.DONE
            index = await pipelines.index(index_id)
            document = await DocumentRepository(session).get_for_update(document_id)
            if index is None or document is None or document.status != JobStatus.READY:
                return Outcome.DONE
            entry.status = JobStatus.PROCESSING
            entry.attempts += 1
            entry.error = None
            sections = sections_from_rows(await DocumentRepository(session).sections(document.id))
            settings = dict(index.config)
            dim = index.embedding_dim
            model_key = index.embedding_model
            title, metadata = document.title, dict(document.meta or {})
            collection_id, project_id = document.collection_id, document.project_id
            await session.commit()

        config = PipelineConfig.model_validate(
            {"cleaning": settings["cleaning"], "chunking": settings["chunking"]}
        )
        strategy = config.chunking.strategy
        started = time.perf_counter()
        try:
            with anyio.fail_after(self.c.settings.job_timeout_s):
                cleaned, _ = await anyio.to_thread.run_sync(
                    clean_sections, sections, cleaning_options(config)
                )
                drafts = await anyio.to_thread.run_sync(
                    chunk_sections, cleaned, self.c.tokens, chunking_options(config)
                )
                embedder = self.c.embedders.get(
                    spec_for_index(model_key, settings, dim), str(project_id)
                )
                contextual = bool(settings["embedding"].get("contextual", True))
                texts = [
                    "\n".join(part for part in (title, d.heading, d.text) if part)
                    if contextual
                    else d.text
                    for d in drafts
                ]
                batches = [
                    await embedder.embed_documents(texts[i : i + EMBED_BATCH])
                    for i in range(0, len(texts), EMBED_BATCH)
                ]
                vectors = np.concatenate(batches) if batches else np.zeros((0, dim), np.float32)
        except TimeoutError:
            await self._fail_entry(index_id, document_id, "Indexing took too long and was stopped.")
            return Outcome.DONE
        except AppError as exc:
            if final_attempt:
                await self._fail_entry(index_id, document_id, exc.message)
                return Outcome.DONE
            await self._requeue_entry(index_id, document_id)
            return Outcome.RETRY
        except Exception:
            log.exception("index_error", index_id=str(index_id), document_id=str(document_id))
            if final_attempt:
                await self._fail_entry(
                    index_id, document_id, "Indexing failed. Try reprocessing the document."
                )
                return Outcome.DONE
            await self._requeue_entry(index_id, document_id)
            return Outcome.RETRY

        elapsed = time.perf_counter() - started
        async with self.c.db.session() as session:
            pipelines = PipelineRepository(session)
            entry = await pipelines.entry_for_update(index_id, document_id)
            if entry is None:
                return Outcome.DONE
            await ChunkRepository(session).replace_for_document(
                index_id=index_id,
                collection_id=collection_id,
                document_id=document_id,
                drafts=drafts,
                embeddings=vectors,
                dim=dim,
                metadata=metadata,
            )
            entry.status = JobStatus.READY
            entry.chunk_count = len(drafts)
            entry.token_count = sum(d.token_count for d in drafts)
            entry.duration_ms = int(elapsed * 1000)
            entry.error = None if drafts else "No text was left to index after cleaning."
            await CollectionRepository(session).bump_corpus_version(collection_id)
            await session.commit()

        metrics.INDEX_ENTRIES.labels("ready").inc()
        metrics.INDEX_DURATION.labels(strategy).observe(elapsed)
        metrics.CHUNKS_WRITTEN.labels(strategy).inc(len(drafts))
        log.info(
            "indexed",
            index_id=str(index_id),
            document_id=str(document_id),
            chunks=len(drafts),
            seconds=round(elapsed, 2),
        )
        return Outcome.DONE

    async def _fail_entry(self, index_id: uuid.UUID, document_id: uuid.UUID, message: str) -> None:
        metrics.INDEX_ENTRIES.labels("failed").inc()
        async with self.c.db.session() as session:
            await PipelineRepository(session).mark_entry(
                index_id, document_id, status=JobStatus.FAILED, error=message[:1000]
            )
            await session.commit()

    async def _requeue_entry(self, index_id: uuid.UUID, document_id: uuid.UUID) -> None:
        async with self.c.db.session() as session:
            await PipelineRepository(session).mark_entry(
                index_id, document_id, status=JobStatus.QUEUED
            )
            await session.commit()

    # Recovery ---------------------------------------------------------------------------

    async def reap_stale(self) -> int:
        """Recover work stuck unfinished: a lost message or a crashed worker.

        Queued work is re-sent only while the queue is empty; with a backlog its message is
        most likely still waiting. Re-sent rows restart their clock, so each is re-sent at
        most once per window, and rows out of attempts are marked failed.
        """
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=self.c.settings.stale_job_minutes)
        idle = await self.c.queue.backlog() == 0
        jobs: list[Job] = []
        reaped = 0
        async with self.c.db.session() as session:
            for document in await DocumentRepository(session).unfinished_before(cutoff):
                if document.status == JobStatus.QUEUED and not idle:
                    continue
                reaped += 1
                if document.attempts >= MAX_ATTEMPTS:
                    document.status = JobStatus.FAILED
                    document.error = "Parsing did not finish after several attempts."
                else:
                    document.status = JobStatus.QUEUED
                    document.updated_at = now
                    jobs.append(Job.parse(document.project_id, document.id))
            pipelines = PipelineRepository(session)
            for entry in await pipelines.unfinished_entries_before(cutoff):
                if entry.status == JobStatus.QUEUED and not idle:
                    continue
                reaped += 1
                if entry.attempts >= MAX_ATTEMPTS:
                    entry.status = JobStatus.FAILED
                    entry.error = "Indexing did not finish after several attempts."
                else:
                    entry.status = JobStatus.QUEUED
                    entry.updated_at = now
                    jobs.append(Job.index(entry.project_id, entry.index_id, entry.document_id))
            evaluations = EvaluationRepository(session)
            run_cutoff = now - timedelta(minutes=self.c.settings.stale_job_minutes * 2)
            for run in await evaluations.unfinished_runs_before(run_cutoff):
                reaped += 1
                if run.attempts >= MAX_ATTEMPTS:
                    run.status = RunStatus.FAILED
                    run.error = "The run did not finish after several attempts."
                    run.finished_at = now
                else:
                    run.status = RunStatus.QUEUED
                    run.updated_at = now
                    jobs.append(Job.evaluate(run.project_id, run.id))
            await session.commit()
        for job in jobs:
            await self.c.queue.enqueue(job)
        if reaped:
            log.info("reaped_stale_work", count=reaped, requeued=len(jobs))
        return reaped


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """What a parse job needs from the document row, read inside the claiming transaction."""

    id: uuid.UUID
    project_id: uuid.UUID
    collection_id: uuid.UUID
    source_type: str
    source_uri: str | None
    storage_key: str | None
    kind: DocumentKind | None
    default_title: str

    @classmethod
    def of(cls, document: Document) -> _Snapshot:
        return cls(
            id=document.id,
            project_id=document.project_id,
            collection_id=document.collection_id,
            source_type=document.source_type,
            source_uri=document.source_uri,
            storage_key=document.storage_key,
            kind=DocumentKind(document.kind) if document.kind else None,
            default_title=document.title,
        )


def _message(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc) or "The document could not be parsed."
