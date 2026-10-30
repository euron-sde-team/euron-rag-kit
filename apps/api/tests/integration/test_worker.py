"""The job worker on the emulator's SQS: parse, index and eval jobs, failures and the reaper."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from ragkit_server.core.config import Settings
from ragkit_server.integrations.queue import Job, SqsQueue
from ragkit_server.models import Collection, Document, EvalRun, IndexEntry, Project, User
from ragkit_server.models.enums import JobStatus, RunStatus
from ragkit_server.schemas.evaluation import DatasetCreate, ItemIn, RunCreate
from ragkit_server.services.container import Container, build_container
from ragkit_server.services.documents import DocumentService, IncomingFile
from ragkit_server.services.evaluation import EvaluationService
from ragkit_server.services.ingestion import IngestionService
from ragkit_server.services.principal import Principal
from ragkit_server.worker import Worker
from tests.integration.conftest import AwsResources, aws_client
from tests.integration.support import HASH_PIPELINE, create_collection, signup

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def sqs(settings: Settings) -> AsyncIterator[Container]:
    """A worker-side container: same database, storage and cache, jobs through SQS."""
    container = build_container(settings.model_copy(update={"queue_backend": "sqs"}))
    yield container
    await container.close()


@pytest.fixture(scope="module")
async def target(
    client: httpx.AsyncClient, sqs: Container
) -> tuple[Principal, Project, Collection]:
    account = await signup(client, "Worker Owner")
    await create_collection(client, account, account.project, "Queued", HASH_PIPELINE)
    async with sqs.db.session() as session:
        user = await session.get(User, uuid.UUID(account.user_id))
        project = (
            await session.execute(select(Project).where(Project.slug == account.project))
        ).scalar_one()
        collection = (
            await session.execute(select(Collection).where(Collection.project_id == project.id))
        ).scalar_one()
    assert user is not None
    return Principal(user=user), project, collection


async def _upload(
    sqs: Container, target: tuple[Principal, Project, Collection], name: str, data: bytes
) -> uuid.UUID:
    principal, project, collection = target
    async with sqs.db.session() as session:
        outcome = await DocumentService(sqs, session).upload(
            project, collection, principal, [IncomingFile(name, data)], {}
        )
    assert outcome.created, outcome.rejected
    return outcome.created[0].id


async def _row(sqs: Container, model: Any, key: Any) -> Any:
    async with sqs.db.session() as session:
        found = await session.get(model, key)
    assert found is not None
    return found


def _depth(queue_url: str) -> tuple[int, int]:
    """(waiting, in flight) messages."""
    attributes = aws_client("sqs").get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return int(attributes["ApproximateNumberOfMessages"]), int(
        attributes["ApproximateNumberOfMessagesNotVisible"]
    )


def _lose_messages(queue_url: str) -> None:
    sqs = aws_client("sqs")
    while messages := sqs.receive_message(
        QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1
    ).get("Messages"):
        for message in messages:
            sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


async def _work_until(
    sqs: Container, finished: Callable[[], Awaitable[bool]], timeout_s: float = 180
) -> None:
    """Run a real worker until `finished`, then stop it the way SIGTERM does."""
    assert isinstance(sqs.queue, SqsQueue)
    worker = Worker(sqs, sqs.queue)
    running = asyncio.create_task(worker.run())
    try:
        deadline = time.monotonic() + timeout_s
        while not await finished():
            assert not running.done(), "the worker stopped on its own"
            assert time.monotonic() < deadline, "the worker did not finish in time"
            await asyncio.sleep(0.5)
    finally:
        worker.stop()
        await asyncio.wait_for(running, timeout=60)


def _document_is(
    sqs: Container, document_id: uuid.UUID, status: JobStatus
) -> Callable[[], Awaitable[bool]]:
    async def check() -> bool:
        async with sqs.db.session() as session:
            document = await session.get(Document, document_id)
            entries = list(
                (
                    await session.execute(
                        select(IndexEntry).where(IndexEntry.document_id == document_id)
                    )
                ).scalars()
            )
        if document is None or document.status != status:
            return False
        return status != JobStatus.READY or (
            bool(entries) and all(e.status == JobStatus.READY for e in entries)
        )

    return check


async def test_parse_and_index_jobs_travel_through_sqs(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    _lose_messages(aws.queue_url)
    document_id = await _upload(
        sqs, target, "notes.md", b"# Notes\n\nPayouts arrive two business days later.\n"
    )
    assert (await _row(sqs, Document, document_id)).status == JobStatus.QUEUED
    assert _depth(aws.queue_url) == (1, 0)

    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.READY))

    document = await _row(sqs, Document, document_id)
    assert document.attempts == 1
    assert document.section_count == 1
    assert _depth(aws.queue_url) == (0, 0)


async def test_an_unreadable_file_fails_once_and_leaves_the_queue(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    broken = b"%PDF-1.7\n" + bytes(range(256)) * 16
    document_id = await _upload(sqs, target, "scan.pdf", broken)
    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.FAILED))
    document = await _row(sqs, Document, document_id)
    assert document.attempts == 1
    assert document.error
    assert _depth(aws.queue_url) == (0, 0)


async def test_evaluation_runs_execute_on_the_worker(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    principal, project, collection = target
    document_id = await _upload(
        sqs, target, "limits.md", b"# Limits\n\nLive mode allows 100 requests per second.\n"
    )
    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.READY))
    async with sqs.db.session() as session:
        evaluation = EvaluationService(sqs, session)
        await evaluation.create_dataset(
            project,
            principal,
            DatasetCreate(
                name="Worker set",
                collection=collection.slug,
                items=[
                    ItemIn(
                        question="What is the live mode rate limit?",
                        expected_sources=[
                            {"document": "limits", "evidence": "100 requests per second"}
                        ],
                        expected_answer="100 requests per second.",
                    )
                ],
            ),
        )
        run = await evaluation.create_run(project, principal, RunCreate(dataset="worker-set"))
    assert _depth(aws.queue_url) == (1, 0)

    async def finished() -> bool:
        return bool(RunStatus((await _row(sqs, EvalRun, run.id)).status).finished)

    await _work_until(sqs, finished)
    done = await _row(sqs, EvalRun, run.id)
    assert done.status == RunStatus.COMPLETED
    assert done.metrics["means"]["hit_rate"] == 1.0


async def test_malformed_messages_are_dropped(sqs: Container, aws: AwsResources) -> None:
    aws_client("sqs").send_message(QueueUrl=aws.queue_url, MessageBody='{"kind": "launch"}')
    assert isinstance(sqs.queue, SqsQueue)
    received = await sqs.queue.receive(max_messages=10, wait_s=1, visibility_s=30)
    assert received == []
    assert _depth(aws.queue_url) == (0, 0)


async def test_the_reaper_resends_work_whose_message_was_lost(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    document_id = await _upload(sqs, target, "lost.md", b"# Lost\n\nThis message never arrives.\n")
    _lose_messages(aws.queue_url)
    async with sqs.db.session() as session:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()

    assert await IngestionService(sqs).reap_stale() == 1
    assert _depth(aws.queue_url) == (1, 0)
    # Its clock restarted: the next round does not send it again.
    assert await IngestionService(sqs).reap_stale() == 0
    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.READY))


async def test_the_reaper_leaves_waiting_work_alone_during_a_backlog(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    document_id = await _upload(sqs, target, "waiting.md", b"# Waiting\n\nStill in the queue.\n")
    async with sqs.db.session() as session:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()
    # Its message is still waiting, so resending would only duplicate it.
    assert await IngestionService(sqs).reap_stale() == 0
    assert _depth(aws.queue_url) == (1, 0)
    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.READY))


async def test_work_out_of_attempts_is_marked_failed(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    document_id = await _upload(sqs, target, "doomed.md", b"# Doomed\n\nNever finishes.\n")
    _lose_messages(aws.queue_url)
    async with sqs.db.session() as session:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status=JobStatus.PROCESSING,
                attempts=3,
                updated_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await session.commit()
    assert await IngestionService(sqs).reap_stale() == 1
    document = await _row(sqs, Document, document_id)
    assert document.status == JobStatus.FAILED
    assert "several attempts" in (document.error or "")
    assert _depth(aws.queue_url) == (0, 0)


async def test_duplicate_deliveries_are_harmless(
    sqs: Container, target: tuple[Principal, Project, Collection], aws: AwsResources
) -> None:
    _, project, _ = target
    document_id = await _upload(sqs, target, "twice.md", b"# Twice\n\nDelivered more than once.\n")
    await sqs.queue.enqueue(Job.parse(project.id, document_id))
    await _work_until(sqs, _document_is(sqs, document_id, JobStatus.READY))
    await _work_until(sqs, lambda: _empty(aws.queue_url))
    document = await _row(sqs, Document, document_id)
    assert document.attempts == 1


async def _empty(queue_url: str) -> bool:
    return _depth(queue_url) == (0, 0)
