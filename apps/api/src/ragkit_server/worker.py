"""The job worker: long-polls SQS and runs parse, index and evaluation jobs.

    python -m ragkit_server.worker

- Message visibility is extended while a job runs, so a long evaluation or a large PDF is
  never handed to a second worker.
- A failure returns the message to the queue with growing back-off; after three receives
  SQS moves it to the dead-letter queue and the row is marked failed.
- SIGTERM stops receiving and lets in-flight jobs finish for a grace period. Jobs still
  running then are cancelled and their messages made visible again at once, so another
  worker picks them up instead of waiting out the visibility timeout: a rolling deploy
  never loses or stalls work. ECS waits stop_timeout (120 s) after SIGTERM, longer than
  the grace period, so the hand-back always happens before the kill.
- One worker at a time (elected through Redis) re-enqueues work stuck unfinished.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal

from prometheus_client import start_http_server

from ragkit_server.core.config import get_settings
from ragkit_server.core.logging import configure_logging, get_logger
from ragkit_server.db.migrate import migrate
from ragkit_server.integrations.queue import ReceivedJob, SqsQueue
from ragkit_server.services.container import Container, build_container
from ragkit_server.services.ingestion import MAX_ATTEMPTS, IngestionService, Outcome

log = get_logger("ragkit.worker")
VISIBILITY_S = 300
SHUTDOWN_GRACE_S = 90
REAPER_INTERVAL_S = 60


class Worker:
    def __init__(self, container: Container, queue: SqsQueue) -> None:
        self.c = container
        self.queue = queue
        self.jobs = IngestionService(container)
        self.concurrency = container.settings.worker_concurrency
        self.stopping = asyncio.Event()
        # Running jobs and the receipt of the message each one came from.
        self.inflight: dict[asyncio.Task[None], str] = {}

    def stop(self) -> None:
        if not self.stopping.is_set():
            log.info("worker_stopping", inflight=len(self.inflight))
            self.stopping.set()

    async def run(self) -> None:
        reaper = asyncio.create_task(self._reaper())
        while not self.stopping.is_set():
            free = self.concurrency - len(self.inflight)
            if free <= 0:
                await asyncio.wait(self.inflight, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                received = await self.queue.receive(
                    max_messages=min(10, free), wait_s=10, visibility_s=VISIBILITY_S
                )
            except Exception:
                log.exception("queue_receive_failed")
                await asyncio.sleep(5)
                continue
            for item in received:
                task = asyncio.create_task(self._handle(item))
                self.inflight[task] = item.receipt
                task.add_done_callback(lambda done: self.inflight.pop(done, None))
        if self.inflight:
            _, unfinished = await asyncio.wait(set(self.inflight), timeout=SHUTDOWN_GRACE_S)
            await self._hand_back(unfinished)
        reaper.cancel()

    async def _hand_back(self, tasks: set[asyncio.Task[None]]) -> None:
        """Cancel jobs that outlived the grace period and release their messages now."""
        receipts = [self.inflight[task] for task in tasks if task in self.inflight]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for receipt in receipts:
            with contextlib.suppress(Exception):
                await self.queue.extend(receipt, 0)
        if receipts:
            log.warning("jobs_handed_back", count=len(receipts))

    async def _handle(self, item: ReceivedJob) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(item.receipt))
        try:
            final = item.receive_count >= MAX_ATTEMPTS
            outcome = await self.jobs.handle(item.job, final_attempt=final)
            if outcome is Outcome.DONE:
                await self.queue.delete(item.receipt)
            else:
                await self.queue.extend(item.receipt, 30 * item.receive_count)
        except Exception:
            log.exception("job_failed", kind=item.job.kind, subject=item.job.subject)
        finally:
            heartbeat.cancel()

    async def _heartbeat(self, receipt: str) -> None:
        while True:
            await asyncio.sleep(VISIBILITY_S / 2)
            with contextlib.suppress(Exception):
                await self.queue.extend(receipt, VISIBILITY_S)

    async def _reaper(self) -> None:
        while True:
            await asyncio.sleep(REAPER_INTERVAL_S)
            try:
                if await self.c.redis.set("lock:reaper", b"1", ex=REAPER_INTERVAL_S - 5, nx=True):
                    await self.jobs.reap_stale()
            except Exception:
                log.exception("reaper_failed")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.migrate_on_boot:
        await migrate(settings)
    container = build_container(settings)
    if not isinstance(container.queue, SqsQueue):
        raise SystemExit(
            "The worker needs QUEUE_BACKEND=sqs. With the inline queue the API runs jobs itself."
        )
    if port := int(os.environ.get("WORKER_METRICS_PORT", "0")):
        start_http_server(port)
    await container.warm_up()
    worker = Worker(container, container.queue)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.stop)
    log.info("worker_started", concurrency=worker.concurrency)
    try:
        await worker.run()
    finally:
        await container.close()
        log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
