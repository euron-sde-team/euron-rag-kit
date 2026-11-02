# Operations

Day-two tasks for a running RAGKit: what to watch, what the alarms mean, how to scale, rotate
keys, back up and recover. The commands assume the AWS deployment from
[deploy-aws.md](deploy-aws.md); the same signals exist on the local stack.

- [Health](#health)
- [Metrics](#metrics)
- [Logs](#logs)
- [Alarms](#alarms)
- [Scaling](#scaling)
- [Work that needs attention](#work-that-needs-attention)
- [Changing models and settings](#changing-models-and-settings)
- [Keys and secrets](#keys-and-secrets)
- [Backups and recovery](#backups-and-recovery)
- [Housekeeping](#housekeeping)
- [Upgrades](#upgrades)

## Health

| Endpoint | Process | Meaning |
| --- | --- | --- |
| `GET /livez` | API | The process answers. The load balancer and the container health check use it |
| `GET /readyz` | API | Database, Valkey, storage and queue all reachable: `200 {"status": "ready", "checks": {...}}`, otherwise `503` with `"status": "degraded"` and the failing check marked `failing` |
| `GET /metrics` | API (inside the VPC only) | Prometheus metrics of that task. The public load balancer answers 404 |
| `:9160/metrics` | worker | Prometheus metrics of that worker; its container health check reads it |
| `GET /env.js` | web | The web app's health check |
| `GET /api/v1/system/info` | API | Which embedding models, rerankers and answerers are available, and the limits in force (the dashboard reads it too) |

In the dashboard, a collection's **Documents** tab shows each document's parse status and the
index state per pipeline version, a pipeline version's page shows its index build progress,
and **Analytics** shows traffic, latency and the share of queries that found nothing.

## Metrics

| Metric | Labels | Watch for |
| --- | --- | --- |
| `ragkit_http_requests_total`, `ragkit_http_request_duration_seconds` | method, route template, status | Error rates and latency per route |
| `ragkit_retrieval_stage_seconds` | stage (`embed`, `vector`, `keyword`, `fusion`, `rerank`, `total`) | Which stage got slow: `vector` after a large ingest (HNSW build pressure), `rerank` when CPU is short |
| `ragkit_queries_total` | kind (`query`, `answer`), mode | Traffic mix |
| `ragkit_answer_duration_seconds` | answerer | A model provider slowing down |
| `ragkit_cache_total` | cache (`embedding`, `query`), result | Hit ratios: a low embedding hit ratio during an index build is normal, a low query hit ratio is normal for varied traffic |
| `ragkit_rerank_fallbacks_total` | | Above zero: the cross-encoder could not load and the lexical reranker is serving |
| `ragkit_documents_parsed_total` | kind, outcome | A rise in `failed` outcomes for one kind (a parser problem) |
| `ragkit_index_entries_total`, `ragkit_index_entry_duration_seconds`, `ragkit_chunks_written_total` | outcome, strategy | Index throughput and failures per chunking strategy |
| `ragkit_eval_runs_total` | outcome | A rise in `failed` runs |

## Logs

Every process logs one JSON object per line: `timestamp`, `level`, `logger`, `event`, and on
the API the `request_id` that is also returned in the `X-Request-Id` header and in every error
body. Values under keys that look sensitive are redacted before a line is written. On AWS each
service writes to its own CloudWatch log group (encrypted with the deployment's KMS key). To
follow one failed request in CloudWatch Logs Insights:

```text
fields @timestamp, level, event, logger
| filter request_id = "<the id from the error>"
| sort @timestamp asc
```

Events worth an alert of your own:

| Event | Level | Meaning |
| --- | --- | --- |
| `unhandled_error` | error | An exception no handler expected; carries the request id |
| `job_failed`, `parse_error`, `index_error`, `eval_run_failed` | error | A job raised; the document, entry or run is marked failed once the attempts are used |
| `queue_receive_failed`, `reaper_failed` | error | The worker could not read the queue, or its stale-work pass raised |
| `readiness_check_failed` | warning | A dependency probe failed (names which) |
| `cross_encoder_unavailable` | warning | The reranker model could not load; queries fall back to the lexical reranker |
| `llm_error` | warning | A model provider call failed |
| `rate_limit_unavailable` | warning | Valkey is unreachable, so serving limits are not counting (sign-in answers 503) |
| `jobs_handed_back` | warning | A stopping worker released unfinished jobs to the queue |
| `reaped_stale_work` | info | The reaper re-enqueued work stuck past `STALE_JOB_MINUTES` |
| `duplicate_delivery_dropped` | info | SQS delivered a job another worker already holds; harmless |

## Alarms

The `observability` module sends these to the SNS topic (and to `alarm_email` when set). Names
are prefixed with the deployment's `name_prefix`:

| Alarm | Meaning | What to do |
| --- | --- | --- |
| `api-5xx`, `web-5xx` | A service returned server errors | Find the `request_id` in the error body or the log, then the `unhandled_error` line |
| `api-unhealthy`, `web-unhealthy` | Tasks are failing the load balancer health check (`/livez`, `/env.js`) | Check the service's events and the task's last log lines; a crash loop is usually configuration (the boot refusal lists every problem) |
| `<service>-cpu`, `<service>-memory` | Sustained above 85% | For the API and workers: both load an embedding model and a reranker, so memory pressure usually means too little `api_memory` or `worker_memory` (or too much `worker_concurrency`). Otherwise add tasks |
| `jobs-backlog` | The oldest queued parse, index or evaluation job has waited more than 10 minutes | Add workers (`worker_max_count`) or raise `worker_concurrency`; check the workers are running at all |
| `jobs-dead-letters` | A job was received three times and never completed | See [Dead letters](#dead-letters) |
| `db-cpu`, `db-storage`, `db-connections` | The database is saturated, filling up or near its connection ceiling | Resize; prune query logs ([Housekeeping](#housekeeping)); check the pool sizes against `max_connections` |

The CloudWatch dashboard named after the deployment shows requests and errors, latency, queue
age and dead letters, the database, and CPU and memory per service.

## Scaling

| Lever | Where | Notes |
| --- | --- | --- |
| API tasks | `api_min_count`, `api_max_count` | Stateless; scale on CPU. Sessions are signed tokens and caches live in Valkey |
| Worker tasks | `worker_min_count`, `worker_max_count` | Stateless; scale on CPU. Indexing is split per (index, document), so a big collection is built in parallel across workers |
| Jobs per worker | `worker_concurrency`, with `worker_cpu` and `worker_memory` | Parsing, embedding and evaluation are CPU bound; each task also holds the embedding model and the reranker in memory |
| Database connections | `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | Keep `tasks x (pool + overflow)` for API and workers together under the instance's `max_connections` |
| Vector search | `hnsw.ef_search` is `max(40, 2 x candidates)` per query | Raise `candidates` in a version's retrieval settings for recall, at the cost of latency |
| Caches | `QUERY_CACHE_TTL_S`, `EMBEDDING_CACHE_TTL_S` | Query results are cached per corpus version, so a change retires them without a scan |

Evaluation runs are one job each, processed question by question, so a large dataset cannot
monopolise a worker's connection pool; several runs execute in parallel across workers.

## Work that needs attention

- **A document is `failed`.** Open it in the dashboard (or `GET .../documents/{id}`): the
  message is safe to show the uploader (an encrypted PDF, a page limit, a bad Word file).
  Fix the file and upload it again, or press **Reprocess** after fixing a transient cause.
- **A version's index is `failed`.** Every entry failed; the entry's `error` names why
  (usually a model provider for `openai:` embeddings, or memory). Fix it and reprocess a
  document, or run `make aws-cli ENV=... ARGS="reindex --collection <slug>"` for the collection.
- **Stuck `processing` or `queued`.** A document, index entry or run whose worker vanished is
  re-enqueued by the reaper once it is older than `STALE_JOB_MINUTES` (15 by default), and
  failed after three attempts. One worker at a time runs the reaper (elected through Valkey).
- **Queries return too little.** `index_status: building` means the version's index is still
  being filled; queries run against what exists so far.
- **A model provider is down.** Model answers return `502 upstream_error`; the extractive
  answerer and every retrieval path keep working, and a model-graded evaluation run falls
  back to the deterministic grade per question and records it.

### Dead letters

Queue messages are only pointers (a document, an index entry or a run), so a dead-lettered
message holds no work. Look at what it names:

```bash
aws sqs receive-message --queue-url <jobs_dlq_url output> \
  --max-number-of-messages 10 --attribute-names All
```

Each of those rows has been marked `failed` with a recorded error by the worker or the reaper;
open it in the dashboard to see which. Once the cause (usually the database, S3 or a bad
deploy) is fixed, reprocess the documents or start the run again, then purge the dead-letter
queue.

## Changing models and settings

- A new **embedding model** or a new chunking setting is a new pipeline version with its own
  index; the old index stays for as long as the collection exists, so budget database storage
  for the indexes you keep.
- A change to **retrieval or answering** only (mode, fusion, reranker, `top_k`) reuses the
  index and is queryable at once.
- Set a model provider with `LLM_PROVIDER`, `LLM_MODEL` and friends
  ([configuration](configuration.md#model-providers)); on AWS put the key in Secrets Manager
  and reference it with `llm_api_key_secret_arn`.
- Bumping `INDEXER_VERSION` (done by whoever changes a chunker or cleaning rule) changes every
  index fingerprint, so the next version you create builds a fresh index; existing indexes
  keep serving.

## Keys and secrets

On AWS the application secrets live in one Secrets Manager secret, `<name_prefix>/app` (JSON
with `SESSION_SECRET` and `API_KEY_PEPPER`). Terraform generates them once and then ignores
their value, so a rotation you make by hand persists.

| Rotate | Effect | How |
| --- | --- | --- |
| `SESSION_SECRET` | Everyone is signed out | Put a new random value (32+ characters) in the secret, then restart the API: `aws ecs update-service --cluster <cluster> --service <api service> --force-new-deployment` |
| `API_KEY_PEPPER` | Every API key stops working; issue new ones | As above, for the API and the workers |
| The KMS key | None | Annual automatic rotation; KMS keeps old key material for decryption, so nothing is re-encrypted |
| Database password | None | RDS rotates it in its managed secret; the app reads it for each new connection |
| The Valkey auth token | Brief reconnects | Replace the token on the replication group, update the `REDIS_URL` secret, restart the services |
| A project API key | Only that key | **Settings, API keys**: revoke it and create a new one |
| The model provider key | Model answers pause until restart | Update the secret, restart the API and the workers |

Rotate one at a time, and never `SESSION_SECRET` and `API_KEY_PEPPER` to the same value
(production refuses that).

## Backups and recovery

| Data | Protection | Recovery |
| --- | --- | --- |
| PostgreSQL (accounts, projects, documents, chunks and vectors, versions, datasets, runs) | Automated RDS backups (3 days in dev, 14 in prod) with point-in-time restore; Multi-AZ in prod | Restore to a new instance, then point `DATABASE_URL` at it |
| Original files and URL snapshots (S3) | Versioning, SSE-KMS, superseded versions kept 90 days | Restore an object version. Because the originals are kept, any document can be parsed again and any index rebuilt |
| An index | Derived data | `reindex` (below) rebuilds every index from the originals if the database was restored without them |
| The KMS key | Deletion window (7 days in dev, 30 in prod) | Cancel a scheduled deletion; without the key the bucket and the queue cannot be read |
| Valkey | None needed: caches, rate limits, the revoked-session list | Rebuilds itself. Sessions that were signed out stay valid until they expire if the list is lost |

```bash
make aws-cli ENV=aws-prod ARGS="reindex"                          # every collection
make aws-cli ENV=aws-prod ARGS="reindex --collection developer-docs"
```

`reindex` parses every document again and, through that, rebuilds the document in every
version's index.

## Housekeeping

- **Query logs** grow with traffic. Analytics reads at most the last 90 days, so older rows
  can be deleted at any time from a host that can reach the database (the master password is
  in the RDS-managed secret):

  ```sql
  DELETE FROM query_logs WHERE created_at < now() - interval '90 days';
  ```

  Set `QUERY_LOG_TEXT=false` to stop keeping the text of queries at all: counts, latency and
  the zero-hit rate keep working, and the top-queries list stays empty.
- **Evaluation runs** are kept until a person deletes them (finished runs only). Each stores
  per-question results, so very large datasets run often add up; delete runs you no longer
  compare against.
- **Accounts and access**: members and keys are managed in **Settings**; **Activity** lists who
  changed what.

## Upgrades

`make aws-deploy` from the new commit; migrations run on boot under an advisory lock, and
workers finish or hand back their jobs before they stop. See
[deploy-aws.md](deploy-aws.md#updating) for rollouts and rollbacks.

Model and library updates (`fastembed`, the ONNX runtime, `tiktoken`) arrive with
`apps/api/uv.lock`; the embedding model, the reranker and the tokenizer are baked into the
image at build time, so a running container never downloads anything. Rebuild the image at
least monthly to pick up security fixes in the base image and the locked dependencies.
