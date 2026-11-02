# API guide

Everything the dashboard does goes through this REST API. [`openapi.json`](openapi.json) is
exported from the application itself (`make openapi`), and a running API serves the same
document interactively at `/docs`. This page covers what the reference does not: how to
authenticate, the conventions every endpoint shares, and the common tasks.

Base URL: `http://localhost:8160` locally, `https://api.<domain>` on AWS. Every path below
starts with `/api/v1`.

- [Authentication](#authentication)
- [Conventions](#conventions)
- [Retrieve passages](#retrieve-passages)
- [Answer with citations](#answer-with-citations)
- [Add content](#add-content)
- [Pipeline versions](#pipeline-versions)
- [Datasets, runs and the gate](#datasets-runs-and-the-gate)
- [Errors](#errors)
- [Python SDK and CLI](#python-sdk-and-cli)

## Authentication

| Caller | How |
| --- | --- |
| The dashboard | `POST /auth/login` sets an `httpOnly` `ragkit_session` cookie (`SameSite=Lax`). Unsafe requests that carry the cookie must come from the web app's origin (`WEB_URL` or `CORS_ORIGINS`), otherwise the answer is `403 csrf` |
| An application, a script or CI | A project API key: `Authorization: Bearer rgk_...`. Owners create keys under **Settings, API keys** (or `POST /projects/{project}/api-keys`); the secret is shown once and only a keyed hash is stored |

A session token (the `token` field of the login response) also works as a bearer token.

A key belongs to one project and carries one role:

| Role | Can |
| --- | --- |
| `viewer` | Read everything, query and answer. The right key for a production application |
| `editor` | Also add content, create pipeline versions and datasets, start evaluation runs and set baselines. The right key for CI |
| `owner` | People only: members, keys, project settings and deletion. API keys never carry this role |

## Conventions

- **Projects and collections** appear in the path by slug or id:
  `/projects/acme-payments/collections/developer-docs/...`. A project you cannot see answers
  `404`, never `403`, so a project's existence is not revealed.
- **Lists** take `limit` and `offset` and return
  `{"items": [...], "total": n, "limit": l, "offset": o}`.
- **Errors** always have one shape, with the request id that also appears in the
  `X-Request-Id` header (send your own `X-Request-Id` to correlate) and in the server log:

  ```json
  {"error": {"code": "invalid_filter", "message": "Unknown operator $regex.", "request_id": "01J...", "details": {"path": "section"}}}
  ```

- **Rate limits** are per minute: sign-in 10 per address, query and answer 600 per person or
  key, ingestion 120 and evaluation runs 30. Over the limit the answer is `429` with
  `Retry-After`, and limited endpoints send `X-RateLimit-Limit`, `X-RateLimit-Remaining`
  and `X-RateLimit-Reset`.
- **Request bodies reject unknown fields** (`422 validation_failed`), so a typo in an option
  is an error and not a silent no-op.
- **Times** are ISO 8601 in UTC.

The examples use `acme-payments`, the project that `make demo` creates.

```bash
API=http://localhost:8160/api/v1/projects/acme-payments
KEY=rgk_...            # the viewer key that make demo printed (editor for the sections that write)
```

## Retrieve passages

```bash
curl -sS -X POST "$API/collections/developer-docs/query" \
  -H "Authorization: Bearer $KEY" -H "content-type: application/json" \
  -d '{"query": "how do I verify webhook signatures", "top_k": 3}'
```

The collection's active pipeline version answers unless the body names another
(`"pipeline_version": 3`). Any retrieval setting of a version can be overridden for one
request without creating a version, and metadata filters narrow the candidates:

```json
{
  "query": "payout schedule",
  "mode": "hybrid",
  "fusion": "rrf",
  "rerank": "cross-encoder",
  "candidates": 40,
  "rerank_candidates": 20,
  "filters": {"audience": "admins", "updated": {"$gte": "2026-01-01"}}
}
```

| Field | Values |
| --- | --- |
| `mode` | `vector`, `keyword`, `hybrid` |
| `fusion` | `rrf`, `weighted` (hybrid only), with `rrf_k` and `vector_weight` |
| `rerank` | `none`, `lexical`, `cross-encoder` |
| `top_k`, `candidates`, `rerank_candidates` | 1 to 50, 1 to 200, 1 to 100 |
| `filters` | `$eq`, `$ne`, `$in`, `$nin`, `$gt`, `$gte`, `$lt`, `$lte`, `$exists`, `$contains`, `$and`, `$or`, `$not` over document metadata, see [the LLD](../architecture/LLD.md#metadata-filters) |
| `document_ids` | restrict to up to 100 documents |
| `use_cache` | `false` skips the result cache (evaluation runs always do) |

The response lists the hits with what every stage thought of them:

```json
{
  "query": "how do I verify webhook signatures",
  "pipeline_version": 2,
  "index_status": "ready",
  "mode": "hybrid",
  "fusion": "rrf",
  "rerank": {"kind": "cross-encoder", "fallback": false},
  "hits": [
    {
      "rank": 1,
      "document_title": "Webhooks",
      "external_id": "webhooks",
      "location": "Verifying signatures",
      "heading": "Verifying signatures",
      "text": "Every webhook request carries an Acme-Signature header ...",
      "score": 0.9999,
      "scores": {"vector": 0.8806, "keyword": 0.4444, "fused": 0.0328, "rerank": 0.9999},
      "ranks": {"vector": 1, "keyword": 1, "fused": 1, "rerank": 1},
      "metadata": {"section": "guides", "updated": "2026-09-15", "audience": "developers"}
    }
  ],
  "candidates": {"vector": 40, "keyword": 12, "fused": 40},
  "timings_ms": {"embed": 4.2, "vector": 13.3, "keyword": 12.0, "fusion": 0.1, "rerank": 648.5, "total": 687.4},
  "cached": false
}
```

`index_status` is `building` while the version's index is still being filled: queries run
against what is indexed so far. `rerank.fallback` is `true` when the cross-encoder could not
load and the lexical reranker served the request. `cached` is `true` when the identical
request was answered from the result cache (entries are retired whenever the corpus changes).

## Answer with citations

```bash
curl -sS -X POST "$API/collections/developer-docs/answer" \
  -H "Authorization: Bearer $KEY" -H "content-type: application/json" \
  -d '{"query": "How do I rotate API keys without downtime?"}'
```

The body is the query body plus `answerer` (`extractive`, `openai`, `ollama`), `model`,
`max_sources` and `context_tokens`. The response carries `answer` text with `[1]`, `[2]`
markers, the `citations` (each with the document, its location and the supporting `quote`),
the `sources` it was given, token `usage` and the full `retrieval` object of the query that
fed it. Markers that point at sources the answer was not given are removed before you see
them. Without a model provider the built-in extractive answerer answers, offline.

## Add content

Text and URL sources are JSON (up to 100 per request); files are multipart (up to 20 per
request, 25 MB each by default):

```bash
curl -sS -X POST "$API/collections/developer-docs/documents/import" \
  -H "Authorization: Bearer $EDITOR_KEY" -H "content-type: application/json" \
  -d '{"items": [
        {"type": "text", "title": "Refund timing", "text": "# Refunds\n\nRefunds take 5 to 10 days.",
         "format": "markdown", "external_id": "refund-timing", "metadata": {"audience": "developers"}},
        {"type": "url", "url": "https://example.com/docs/payouts", "metadata": {"section": "guides"}}
      ]}'

curl -sS -X POST "$API/collections/developer-docs/documents" \
  -H "Authorization: Bearer $EDITOR_KEY" \
  -F "files=@guide.pdf" -F "files=@notes.md" -F 'metadata={"audience": "developers"}'
```

Both answer `201` with `{"created": [...], "duplicates": [...], "rejected": [...]}`. A file
whose bytes were already added to the collection is reported as a duplicate, and a rejected
source names the reason (`unsupported_media_type`, `payload_too_large`, a URL that points at
a private address). Documents are parsed once and then indexed for every pipeline version;
poll `GET .../documents?status=queued` (or `processing`) until it is empty, and
`GET .../pipelines/{n}` for the version's `index.status`. `external_id` is how evaluation
datasets refer to a document, so give documents stable ids.

## Pipeline versions

A version is an immutable configuration; changing anything creates version N+1:

```bash
curl -sS -X POST "$API/collections/developer-docs/pipelines" \
  -H "Authorization: Bearer $EDITOR_KEY" -H "content-type: application/json" \
  -d '{
        "name": "Smaller chunks",
        "description": "192-token chunks, same reranker",
        "config": {"chunking": {"strategy": "recursive", "chunk_tokens": 192, "overlap_tokens": 24},
                   "retrieval": {"mode": "hybrid", "rerank": "cross-encoder"}},
        "activate": false
      }'
```

Every field has a default, so `{}` is a valid configuration (the
[LLD](../architecture/LLD.md#pipeline-configuration) lists them all). The response tells
you whether the version `shared_with` another version's index (only retrieval or answering
changed, so it is queryable at once) or builds a new one (`index.progress` follows it).
`POST .../pipelines/preview` chunks a document or some text with a candidate configuration and
returns the chunks and their size statistics without saving anything;
`POST .../pipelines/{n}/activate` makes a version the one that serves queries by default;
`GET .../pipelines/{n}/chunks` browses a version's chunks.

## Datasets, runs and the gate

A dataset is a list of questions, each with the document (by `external_id`) and the evidence
sentence that answers it, and optionally a reference answer. Import JSONL, one object per
line:

```json
{"question": "What is the request rate limit in live mode?", "expected_sources": [{"document": "rate-limits", "evidence": "Requests per second: 100"}], "expected_answer": "100 requests per second.", "tags": ["lookup", "numeric"]}
```

```bash
# From the repository root: create a dataset with the sample questions (or POST
# .../datasets/{slug}/items to add questions to an existing one).
curl -sS -X POST "$API/datasets" -H "Authorization: Bearer $EDITOR_KEY" \
  -H "content-type: application/json" \
  -d "$(python3 - <<'PY'
import json
items = [json.loads(line) for line in open("samples/datasets/smoke.jsonl")]
print(json.dumps({"name": "Payments smoke", "slug": "payments-smoke", "collection": "developer-docs", "items": items}))
PY
)"

# Start a run of the dataset against version 2; the answer is 201 with the queued run.
RUN=$(curl -sS -X POST "$API/eval-runs" -H "Authorization: Bearer $EDITOR_KEY" \
  -H "content-type: application/json" \
  -d '{"dataset": "payments-smoke", "pipeline_version": 2, "label": "v2 nightly", "k": 5}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# Poll until status is completed or failed; metrics are the means over the questions.
curl -sS "$API/eval-runs/$RUN" -H "Authorization: Bearer $KEY"
```

| Run option | Meaning |
| --- | --- |
| `pipeline_version` | The version to measure (the active one by default) |
| `k` | The cutoff for the metrics (default 5) |
| `retrieval`, `answer` | Overrides for this run only, recorded in its configuration snapshot |
| `answers` | `false` measures retrieval only |
| `grader` | `deterministic` (default) or `model` (needs a model provider) |

A finished run's `metrics` object holds `means` (`hit_rate`, `context_recall`,
`context_precision`, `mrr`, `ndcg`, `faithfulness`, `answer_relevance` and
`answer_correctness`), `counts` (how many questions each mean is over), `questions`, `failed`,
`latency_ms` (`p50`, `p95`, `mean`) and `by_tag`, the same means per tag.
`GET .../eval-runs/{id}/results` lists every question with the retrieved chunks, the answer,
its citations, its metrics and its grading. How each metric is computed is in the
[LLD](../architecture/LLD.md#metrics).

**Compare** two to four runs: `GET .../eval-runs/compare?ids=<reference>,<other>` returns the
metric deltas against the first run, the configuration differences and, for runs of one
dataset, the questions that improved or regressed.

**Gate**: `POST .../eval-runs/{id}/baseline` marks a run as its dataset's baseline, and
`POST .../eval-runs/{id}/gate` checks a run against floors and that baseline:

```bash
curl -sS -X POST "$API/eval-runs/$RUN/baseline" -H "Authorization: Bearer $EDITOR_KEY"   # once

curl -sS -X POST "$API/eval-runs/$LATER_RUN/gate" -H "Authorization: Bearer $KEY" \
  -H "content-type: application/json" -d '{"min": {"hit_rate": 0.85}, "max_drop": 0.03}'
```

```json
{
  "passed": true,
  "run_id": "01a19c33-...",
  "run_status": "completed",
  "baseline_run_id": "01a19c28-...",
  "checks": [
    {"metric": "hit_rate", "kind": "min", "threshold": 0.85, "value": 1.0, "baseline": null,
     "passed": true, "message": "1.000 meets 0.850"},
    {"metric": "mrr", "kind": "max_drop", "threshold": 0.03, "value": 0.968, "baseline": 0.968,
     "passed": true, "message": "+0.000 against the baseline, within the allowed drop of 0.030"}
  ]
}
```

A number for `max_drop` applies to every metric the run measured; an object picks metrics
(`{"max_drop": {"mrr": 0.02}}`). A drop check on a dataset with no baseline run fails with
"no baseline run", and so does a metric the run did not measure, so a gate cannot pass by
accident. Thresholds left out of the body come from the dataset's own gate settings. In CI use
`ragkit eval gate`, which starts the run, waits, calls this endpoint, writes a Markdown report
and exits 0 (pass), 1 (regression) or 2 (the run could not be evaluated).

## Errors

| Status | Codes |
| --- | --- |
| 400 | `bad_request` |
| 401 | `unauthorized`, `invalid_credentials`, `invalid_api_key` |
| 403 | `forbidden`, `csrf` |
| 404 | `not_found` |
| 409 | `conflict`, `duplicate_external_id` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type`, `content_mismatch` |
| 422 | `validation_failed`, `invalid_filter`, `invalid_pipeline`, `provider_unavailable`, `last_owner` |
| 429 | `rate_limited` |
| 502 | `upstream_error` (a model provider failed; retrieval and the extractive answerer keep working) |
| 503 | `service_unavailable` |

A `422` carries `details` that point at the field or the filter path that is wrong. A `429`
was refused before any work happened, so retrying it is always safe, and so is retrying any
read after a `502` or `503`; the SDK does both. It does not retry a `POST` after a gateway
error, because that request may have run (a second run would be a second experiment).

## Python SDK and CLI

The SDK in [`sdk/python`](../../sdk/python) wraps all of this, including waiting for indexing
and runs, retries with back-off and typed errors:

```python
from ragkit import RAGKit

rk = RAGKit()  # RAGKIT_URL, RAGKIT_API_KEY and RAGKIT_PROJECT from the environment
docs = rk.collection("developer-docs")
result = docs.answer("How long do refunds take?", rerank="cross-encoder")
print(result.answer, [c.document_title for c in result.citations])

run = rk.evals.run("support-golden", pipeline_version=3)   # waits for the worker
print(run.means["hit_rate"], run.means["mrr"])
```

The `ragkit` command line (`query`, `answer`, `ingest`, `eval import`, `eval run`,
`eval gate`) installs with it; see the [SDK README](../../sdk/python/README.md).
