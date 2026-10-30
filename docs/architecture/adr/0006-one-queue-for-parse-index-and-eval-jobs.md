# ADR 0006: One SQS queue with a dead-letter queue for parse, index and evaluation jobs

## Status

Accepted.

## Context

Three kinds of background work exist: parsing a document (once), indexing a document into
one index (once per index), and running an evaluation (once per run). They have different
durations, from milliseconds to many minutes, but the same needs: durable delivery, retries
with back-off, a place for poison messages, and workers that can scale out and drain safely
during deploys.

## Decision

- One standard SQS queue carries all three job kinds. Messages contain **ids only**
  (`{"kind": "index", "project_id", "index_id", "document_id"}`); the worker reloads state
  from Postgres.
- Every job **claims its row** (`SELECT ... FOR UPDATE`) and is **idempotent**: a duplicate
  delivery of a finished job is a no-op, an index job replaces the document's chunks in one
  transaction, an evaluation run upserts results per question and resumes.
- The worker extends a message's visibility while a job runs, returns failures with a
  growing delay, and after three receives SQS moves the message to the dead-letter queue,
  where alarms fire.
- On SIGTERM the worker stops receiving, gives in-flight jobs a grace period, then cancels
  what is left and makes those messages visible again at once, inside ECS's stop timeout.
- A leader elected through Valkey runs a reaper every minute: rows stuck unfinished past
  their window are re-enqueued (unless their message is still waiting in a backlog) or
  failed after three attempts. This recovers work whose message was lost, for example when
  the database commit succeeded but the enqueue did not.
- In development and tests, `QUEUE_BACKEND=inline` runs the same handlers inside the API.

## Consequences

Positive:

- One queue, one worker image, one set of alarms; workers scale on one metric.
- The database is the source of truth, so message loss and duplication are both harmless.
- Rolling deploys never lose work and do not stall it for a visibility timeout.

Trade-offs:

- A long evaluation occupies one worker slot; concurrency per worker is bounded and runs
  across workers proceed in parallel, so ingestion is delayed, not blocked.
- Priorities between job kinds are not expressed; separate queues would be the next step if
  that becomes necessary.

## Alternatives considered

- **Postgres as the queue** (`SKIP LOCKED`). Fewer moving parts, but the production
  deployment already has SQS with redrive, visibility and metrics for free.
- **A queue per job kind.** Independent scaling and priorities, at the cost of more
  infrastructure before there is a measured need.
- **Celery or another task framework.** Adds a broker abstraction and conventions without
  solving the idempotency that matters here.
