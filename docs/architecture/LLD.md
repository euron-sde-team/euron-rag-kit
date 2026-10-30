# Low-Level Design

How the pieces in the [High-Level Design](HLD.md) are built: the modules, the pipeline
configuration, the algorithms behind chunking, retrieval and evaluation, the jobs, the
caches and the web app. Tables and indexes are in the [Data Model](data-model.md).

- [Repository layout](#repository-layout)
- [API layers](#api-layers)
- [Pipeline configuration](#pipeline-configuration)
- [Ingestion](#ingestion)
- [Embeddings](#embeddings)
- [Retrieval](#retrieval)
- [Answers and citations](#answers-and-citations)
- [Evaluation](#evaluation)
- [Jobs and the worker](#jobs-and-the-worker)
- [Caching and rate limits](#caching-and-rate-limits)
- [Authentication and access](#authentication-and-access)
- [Errors](#errors)
- [Python SDK and CLI](#python-sdk-and-cli)
- [Web app](#web-app)

## Repository layout

```text
apps/api/src/ragkit_server/
├── main.py            app factory: middleware, routers, lifespan
├── worker.py          SQS consumer for parse, index and eval jobs
├── cli.py             typer CLI: migrate, users, demo, reindex, openapi
├── core/              config, logging, errors, request context, security, rate limits, metrics, text
├── db/                engine, sessions, declarative base, column types, migrations runner
├── models/            SQLAlchemy models, one module per aggregate
├── schemas/           Pydantic request and response models, the pipeline configuration
├── repositories/      the only code that touches the database
├── services/          business rules and transactions
├── api/               routes and dependencies
├── ingestion/         sniffing, parsers, cleaning, chunkers (pure)
├── retrieval/         fusion, filters, rerankers, context packing (pure)
├── ai/                tokens, embeddings, answerers, citations, the model judge
├── evaluation/        relevance, metrics, aggregation, comparison, gate (pure)
├── integrations/      storage, job queue, URL fetcher, AWS clients
├── migrations/        Alembic environment and revisions
└── demo/              the demo corpus definition and seeder
```

## API layers

| Layer | May import | Must not |
| --- | --- | --- |
| `api/routes` | schemas, services, `api/deps` | touch a session, a repository or Redis directly |
| `services` | repositories, `ingestion`, `retrieval`, `ai`, `evaluation`, `integrations`, `core` | import FastAPI |
| `repositories` | models, `db` | commit, call a service, or skip the `project_id` filter |
| `ingestion`, `retrieval`, `evaluation` | `core`, each other's types | perform I/O |

A service method that writes opens and commits its own transaction; routes never commit.
Expensive process-wide objects (pools, models, HTTP clients) live in one `Container` built at
startup; services are cheap per-request objects around one session.

## Pipeline configuration

A pipeline version's `config` is validated by `schemas/pipeline.py` and stored as JSONB. All
fields have defaults, so `{}` is a valid configuration.

```json
{
  "cleaning": {
    "normalize_unicode": true,
    "collapse_whitespace": true,
    "strip_boilerplate": false,
    "drop_duplicate_blocks": false,
    "redact_emails": false,
    "min_block_chars": 0
  },
  "chunking": {
    "strategy": "recursive",
    "chunk_tokens": 300,
    "overlap_tokens": 40,
    "sentences_per_chunk": 2,
    "window_sentences": 2
  },
  "embedding": { "model": "bge-small-en-v1.5", "contextual": true },
  "retrieval": {
    "mode": "hybrid",
    "top_k": 5,
    "candidates": 40,
    "fusion": "rrf",
    "rrf_k": 60,
    "vector_weight": 0.5,
    "rerank": "none",
    "rerank_candidates": 20
  },
  "answer": { "answerer": "extractive", "model": null, "max_sources": 5, "context_tokens": 1800 }
}
```

| Section | Field | Values | Notes |
| ------- | ----- | ------ | ----- |
| chunking | `strategy` | `fixed`, `recursive`, `sentence_window` | see [Chunkers](#chunkers) |
| chunking | `chunk_tokens` | 32 to 2048 | target size for `fixed` and `recursive` |
| chunking | `overlap_tokens` | 0 to half of `chunk_tokens` | |
| chunking | `sentences_per_chunk`, `window_sentences` | 1 to 8, 0 to 8 | `sentence_window` only |
| embedding | `model` | a registry key, or a provider model name | with `provider` `openai` or `ollama` and `dim` for unregistered models |
| embedding | `contextual` | bool | embed `title + heading + text` instead of `text` |
| retrieval | `mode` | `vector`, `keyword`, `hybrid` | |
| retrieval | `fusion` | `rrf`, `weighted` | hybrid only |
| retrieval | `rerank` | `none`, `lexical`, `cross-encoder` | |
| answer | `answerer` | `extractive`, `openai`, `ollama` | model answerers need the provider configured |

**Index fingerprint.** `sha256(canonical_json({cleaning, chunking (only the fields the
strategy uses), embedding (resolved provider, model, dim, contextual)}) + INDEXER_VERSION)`.
`INDEXER_VERSION` is a constant bumped whenever cleaning or chunking code changes its output,
so an upgrade never silently mixes chunks from two algorithms in one index. Versions whose
fingerprints match share an index.

**Retrieval overrides.** Query requests and evaluation runs may override any `retrieval`
field and the answer's `answerer`, `max_sources` and `context_tokens`. Index settings cannot
be overridden; they define the index.

## Ingestion

### Loaders

| Source | Intake (api) | Parse job (worker) |
| ------ | ------------ | ------------------ |
| File | multipart upload, extension and magic bytes must agree, size limit, SHA-256 dedupe per collection, original to S3 under `projects/<p>/collections/<c>/documents/<d>/original<ext>` | read from S3, parse by kind |
| URL | `http` or `https` URL validated, document created as `queued` | fetch with the SSRF guard, snapshot to S3, detect kind from `Content-Type` (HTML, Markdown, text, PDF), parse |
| Text | JSON `{title, text}`, stored to S3 as `original.txt` (or `.md` with `format: markdown`) | parse as text or Markdown |

**URL fetch guard** (`integrations/fetcher.py`): only `http` and `https`, ports 80, 443 and
8000 to 9999; the host is resolved and every address must be public (not private, loopback,
link-local, multicast, reserved, or the metadata address `169.254.169.254`) unless
`URL_FETCH_ALLOW_PRIVATE=true`; redirects are followed manually, at most 3, re-checking each
hop; body capped at `MAX_UPLOAD_MB`, 20 s timeout; the response must be a supported type.

### Parsers

`ingestion/parsers/` turns bytes into `ParsedDocument(title, sections[blocks])`. A section is
a page (PDF), or the part of a document under a top-level heading (Markdown, HTML, Word,
text); a block is a paragraph, list item, table row ("Column: value; ...") or heading with
its level. Supported kinds: `pdf`, `docx`, `md`, `html`, `txt`, `csv`.

### Cleaning

Applied per document to the parsed blocks, in this order, each switchable:

1. `normalize_unicode`: NFKC (folds PDF ligatures), removes soft hyphens and zero-width
   characters.
2. `collapse_whitespace`: single spaces, trimmed lines.
3. `strip_boilerplate`: drops short blocks (at most 120 characters) whose digit-masked text
   repeats in at least half of the document's sections (and at least 3), which is what page
   headers and footers look like.
4. `drop_duplicate_blocks`: keeps the first of identical body blocks.
5. `redact_emails`: replaces addresses with `[email]`.
6. `min_block_chars`: drops body blocks shorter than N characters (headings are kept).

### Chunkers

All three return `ChunkDraft(section_ordinal, ordinal, heading, location, text, context,
char_start, char_end, token_count)`. `text` is what gets embedded and keyword-indexed;
`context` is what an answerer and the relevance judge see (equal to `text` unless the
strategy says otherwise).

- **fixed**: the document's cleaned text as one stream, cut into windows of `chunk_tokens`
  tokens with `overlap_tokens` overlap, snapped to word boundaries. Ignores structure on
  purpose: it is the baseline every other strategy is measured against.
- **recursive**: chunks never cross a section. Blocks are packed up to `chunk_tokens`; a
  block that is too long is split at sentence boundaries, a sentence that is still too long
  at word boundaries. Consecutive chunks overlap by whole units up to `overlap_tokens`, and a
  heading never ends a chunk: it moves forward to the text it introduces. Each chunk carries
  its heading path (`Webhooks > Verifying signatures`).
- **sentence_window**: each chunk is `sentences_per_chunk` consecutive sentences of one
  section (sentences under 5 words merge with the next); its `context` is that span widened
  by `window_sentences` sentences on each side within the section. Small units retrieve
  precisely; the wider window gives the answerer enough to work with.

Token counts use tiktoken `o200k_base`, or four characters per token if the encoding is not
available (logged once).

### Index entries

`index_documents(index_id, document_id)` is the unit of indexing work: status, chunk count,
tokens, attempts, error. An index job loads the document's sections, cleans, chunks, embeds
in batches of 64 and, in one transaction, deletes that document's chunks in that index,
inserts the new ones, marks the entry `ready` and bumps the collection's `corpus_version`.
An index's status is derived from its entries: `building` while any is queued or processing,
`ready` when all are ready, `failed` only when every entry failed.

## Embeddings

`ai/embeddings.py` defines `Embedder` (`embed_documents`, `embed_query`) and a registry:

| Key | Provider | Dim | Shipped in the image |
| --- | -------- | --- | -------------------- |
| `hash-384` | deterministic signed feature hashing of stemmed words and word pairs | 384 | yes (no model) |
| `bge-small-en-v1.5` | fastembed ONNX `BAAI/bge-small-en-v1.5`, query instruction prefix | 384 | yes |
| `all-minilm-l6-v2` | fastembed `sentence-transformers/all-MiniLM-L6-v2` | 384 | downloaded on first use |
| `nomic-embed-text-v1.5` | fastembed `nomic-ai/nomic-embed-text-v1.5-Q`, task prefixes | 768 | downloaded on first use |
| `openai:text-embedding-3-small` | OpenAI-compatible `/embeddings` | 1536 | needs `EMBEDDINGS_API_KEY` |
| `ollama:nomic-embed-text` | Ollama `/api/embed` | 768 | needs `OLLAMA_URL` |

Unregistered models are allowed with `provider` and `dim`. Supported widths are 384, 768,
1024 and 1536: each has a partial HNSW index (see the data model). Every vector is
L2-normalised, so cosine similarity is a dot product. An `EmbedderPool` in the container
creates each embedder once per process; a read-through Redis cache wraps all of them with the
key `emb:<model>:<dim>:<doc|query>:<sha256(text)>`.

## Retrieval

`services/retrieval.py` orchestrates; the math is in `retrieval/`.

1. Resolve the collection, the pipeline version (active unless named) and its index; merge
   the request's overrides into the version's retrieval defaults.
2. Look up the result cache (skipped by evaluation runs).
3. **Vector candidates** (modes `vector`, `hybrid`): embed the query, then
   `ORDER BY embedding::vector(D) <=> :q` over `chunks WHERE index_id = :i AND embedding_dim
   = D AND <filters>` with `hnsw.ef_search = max(40, 2 x candidates)` and
   `hnsw.iterative_scan = relaxed_order`. `D` is a SQL literal from the supported widths,
   never a parameter, so the planner can match the partial index on every execution.
4. **Keyword candidates** (modes `keyword`, `hybrid`): an OR `tsquery` over the query's
   stemmed content words ranked by `ts_rank_cd(tsv, q, 32)`, same filters.
5. **Fusion** (hybrid). With `w = vector_weight`:
   - RRF: `score(d) = 2w / (k + rank_v(d)) + 2(1 - w) / (k + rank_k(d))`, ranks from 1, a
     missing rank contributes 0. With `w = 0.5` this is standard RRF.
   - Weighted: each list's scores are min-max normalised to [0, 1] (all equal: 1), then
     `score(d) = w * v(d) + (1 - w) * k(d)`, missing is 0.
6. **Rerank** the top `rerank_candidates`: the cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`
   via fastembed, on `heading + text`), or the lexical reranker: BM25 over the candidate set
   (k1 1.2, b 0.75, IDF `ln(1 + (N - n + 0.5) / (n + 0.5))`) plus 0.5 per query bigram
   present, 0.3 times the heading's share of query terms, and 1.0 when an identifier from the
   query (`ACME-4011`, `max_retries`) appears verbatim, normalised by the maximum. If the
   cross-encoder cannot load, the lexical reranker runs and the response says
   `rerank.fallback: true`.
7. Return the top `top_k` hits with `scores` (vector, keyword, fused, rerank) and `ranks` per
   stage, per-stage timings, the version and index used, and whether it came from cache.

### Metadata filters

`retrieval/filters.py` compiles a JSON filter into a SQLAlchemy expression over
`chunks.metadata` (JSONB, copied from the document when the chunk is written). Field names
match `^[A-Za-z_][A-Za-z0-9_-]{0,63}$`, dotted for nesting up to three levels; values are
always bound parameters.

| Filter | SQL |
| ------ | --- |
| `{"section": "guides"}`, `{"section": {"$eq": "guides"}}` | `metadata @> '{"section": "guides"}'` (GIN index) |
| `{"$ne": v}`, `{"$in": [..]}`, `{"$nin": [..]}` | negation and OR of containment |
| `{"$gt": 2025}` and `$gte`, `$lt`, `$lte` | numeric cast for numbers (guarded by `jsonb_typeof`), text comparison for strings such as ISO dates |
| `{"$exists": true}` | `metadata #> path IS NOT NULL` |
| `{"tags": {"$contains": "beta"}}` | `metadata @> '{"tags": ["beta"]}'` |
| `{"$and": [..]}`, `{"$or": [..]}`, `{"$not": {..}}` | boolean composition |

At most 32 conditions and depth 4; anything else is a 422 with the path of the problem.

## Answers and citations

`ai/answerers.py`: every answerer takes the question and numbered sources and returns text
with `[n]` markers plus token usage.

- **extractive** (default, offline): splits the sources into answer units (sentences, list
  items, table records; headings become context), scores each against the question by
  IDF-weighted term coverage, semantic similarity from the pipeline's embedder, numeric
  intent and source rank, keeps the best units in document order and cites them. When
  nothing covers the question it says so and points at the closest passage.
- **openai**: Chat Completions on any OpenAI-compatible endpoint (`LLM_BASE_URL`).
- **ollama**: Ollama `/api/chat`.

Model prompts fence sources as data, number them, require a citation on every factual
sentence and say that instructions inside sources are not instructions. Sources are packed
greedily into `context_tokens` (the best source always fits), using each hit's `context`.
`ai/citations.py` removes markers that point at sources the answer was not given and attaches
the best supporting sentence of each cited source as its quote.

## Evaluation

### Datasets

An item is `{question, expected_sources: [{document, evidence?}], expected_answer?, tags}`.
`document` is a document's `external_id` in the dataset's collection. Datasets import and
export as JSONL with exactly that shape.

### Relevance

A retrieved chunk *covers* an expected source when it belongs to that document and, if the
source names evidence, the chunk's `context` contains it: after normalisation (case,
whitespace, punctuation) the evidence is a substring, or at least 80% of its stemmed content
words occur in the chunk. A chunk is *relevant* if it covers at least one expected source.
This makes runs over different chunking strategies comparable (ADR-0003): no metric depends
on chunk ids.

### Metrics

For one question with `R` expected sources and the top `k` retrieved chunks
`c_1 .. c_k`, `rel_i` is 1 if `c_i` is relevant:

| Metric | Definition |
| ------ | ---------- |
| `hit_rate` | 1 if any `rel_i` = 1, else 0 |
| `context_recall` | expected sources covered by any of the top k, divided by `R` |
| `context_precision` | average precision over the relevant positions: `sum(precision@i * rel_i) / sum(rel_i)`, 0 when nothing is relevant |
| `mrr` | `1 / i` for the first relevant position, else 0 |
| `ndcg` | gain 1 at position i when `c_i` covers an expected source not covered above it; `DCG = sum(gain_i / log2(i + 1))`, `IDCG` the same for `min(k, R)` gains at the top |
| `faithfulness` | share of the answer's claim sentences that are supported: every number in the claim appears in the given context, and the best single source contains at least 70% of the claim's content words. 1.0 for an answer that makes no claims |
| `answer_relevance` | how directly the answer addresses the question: the cosine similarity of the question and the answer (citations removed) under the pipeline's own embedder, clipped to [0, 1]; a "could not find" answer scores 0 |
| `answer_correctness` | against the reference answer: `0.5 * F2 + 0.5 * fact_recall` when the reference has facts (numbers, identifiers such as `ACME-4011`), else `F2`. F2 is the recall-weighted F-score of stemmed content words; a "could not find" answer scores 0 |

With `grader: model` the run asks the configured judge model for `faithfulness`,
`answer_relevance` and `answer_correctness` (0 to 1, with a reason) and falls back to the
deterministic grade for an item if the judge's reply cannot be parsed, recording
`grader_fallback`.

### Aggregation and comparison

A run's `metrics` are the means of each metric over the questions it applies to (retrieval
metrics need expected sources, correctness needs a reference answer), the number of questions
behind each mean, latency p50 and p95, and the same means per tag. Comparing runs (2 to 4)
returns every run's metrics with deltas against the first, a flattened diff of the
configuration snapshots, and, for runs of the same dataset, per-question rows classified as
improved, regressed or unchanged by the mean of their `ndcg`, `context_recall` and
`answer_correctness` (a change over 0.05 counts).

### Gate

`evaluation/gate.py`: `check(candidate, baseline, min, max_drop)` returns one check per
threshold. A floor passes when `value >= min`; a drop check passes when
`value >= baseline - max_drop`. A metric the run did not measure fails its check. When the
request gives no thresholds, the dataset's stored `gate` settings apply, and the baseline is
the dataset's baseline run unless another run is named.

## Jobs and the worker

One SQS queue (ADR-0006). Messages carry ids only:

```json
{"kind": "parse", "project_id": "...", "document_id": "..."}
{"kind": "index", "project_id": "...", "index_id": "...", "document_id": "..."}
{"kind": "eval", "project_id": "...", "run_id": "..."}
```

| Job | Claim | Idempotency |
| --- | ----- | ----------- |
| parse | `SELECT ... FOR UPDATE` on the document, `queued` to `processing` | a `ready` document is skipped; on success every index entry of the document is reset to `queued` and re-enqueued |
| index | the entry row `FOR UPDATE` | a `ready` entry is skipped; chunks are replaced in one transaction |
| eval | the run row `FOR UPDATE`, `queued` to `running` | a finished run is skipped; results are upserted per item, so a retried run resumes |

The worker long-polls with bounded concurrency, extends a message's visibility every 150 s
while it works, returns failures with a growing delay, and after three receives SQS moves the
message to the dead-letter queue. On SIGTERM it stops receiving and gives in-flight jobs 90
seconds; jobs still running are then cancelled and their messages made visible at once, so
another worker resumes them immediately. ECS gives the worker a 120 second stop timeout, so
this hand-back always happens before the task is killed. A leader elected through Redis (`SET NX EX`) runs the
reaper every minute: documents, entries and runs stuck unfinished past their window are
re-enqueued, or failed after three attempts. In development and tests `QUEUE_BACKEND=inline`
runs the same handlers as background tasks in the API process.

## Caching and rate limits

| Key | Value | TTL | Invalidation |
| --- | ----- | --- | ------------ |
| `emb:<project>:<model>:<dim>:<kind>:<sha256>` | float32 bytes | 30 days | content-addressed, scoped to the project |
| `q:<project>:<collection>:<corpus_version>:<sha256(request)>` | retrieval response | 5 minutes | `corpus_version` changes with every chunk write or document delete |
| `rl:<bucket>:<principal>:<window>` | counter | window + 1 s | fixed window |
| `session:revoked:<jti>` | 1 | token lifetime | |
| `apikey:touched:<id>` | 1 | 60 s | throttles `last_used_at` writes |

Rate limits per minute: login 10 per IP, query and answer 600 per principal, ingest 120,
evaluation runs 30. If Valkey cannot be reached, the serving limits let requests through
uncounted (logged as `rate_limit_unavailable`) while sign-in answers 503: password guessing
is never left unthrottled.

## Authentication and access

- Passwords: Argon2id. Sessions: HS256 JWT in an httponly cookie (or `Authorization: Bearer`),
  with a `jti` denylist for sign-out and a per-user `session_version` for sign-out
  everywhere. Cookie requests with unsafe methods must come from an allowed origin.
- API keys: `rgk_<prefix>_<secret>`, bound to one project with role `viewer` or `editor`;
  only `HMAC-SHA256(pepper, secret)` is stored.
- Roles: `viewer` reads everything and queries; `editor` also ingests, creates versions,
  datasets and runs; `owner` also manages members, keys and deletion.
- `ProjectAccess(minimum_role)` resolves `{project}` (id or slug) and the caller's role;
  non-members get 404 so a project's existence is not revealed.

## Errors

Services raise typed errors from `core/errors.py`; handlers render
`{"error": {"code", "message", "request_id", "details?"}}`.

| Status | Codes |
| ------ | ----- |
| 400 | `bad_request` |
| 401 | `unauthorized`, `invalid_credentials`, `invalid_api_key` |
| 403 | `forbidden`, `csrf` |
| 404 | `not_found` |
| 409 | `conflict`, `duplicate_external_id` |
| 413 | `payload_too_large` |
| 415 | `unsupported_media_type`, `content_mismatch` |
| 422 | `validation_failed`, `invalid_filter`, `invalid_pipeline`, `provider_unavailable`, `last_owner` |
| 429 | `rate_limited` |
| 502 | `upstream_error` |
| 503 | `service_unavailable` |

## Python SDK and CLI

`sdk/python` ships `euron-ragkit`, imported as `ragkit`:

| Module | Contents |
| ------ | -------- |
| `client.py` | `RAGKit(base_url, api_key, project)`, `rk.collection(slug)` with `add_texts`, `add_files`, `add_urls`, `documents`, `wait_until_indexed`, `query`, `answer`, `pipelines`, `pipeline`, `create_pipeline`, `activate`; `rk.evals` with `datasets`, `create_dataset`, `import_items`, `run`, `wait`, `results`, `compare`, `gate`, `set_baseline` |
| `models.py` | Pydantic models for every response the SDK returns |
| `errors.py` | `RAGKitError(status, code, message, request_id)` and subclasses |
| `cli.py` | `ragkit query`, `ragkit answer`, `ragkit ingest`, `ragkit eval import`, `ragkit eval run`, `ragkit eval gate` |

Configuration comes from arguments or `RAGKIT_URL`, `RAGKIT_API_KEY`, `RAGKIT_PROJECT`.
`ragkit eval gate` exits 0 when every check passes, 1 on a regression and 2 when the run could
not be evaluated, and can write the verdict as Markdown or JSON for CI annotations.

## Web app

Next.js App Router with client-side data fetching through TanStack Query; the API URL comes
from `/env.js` at runtime.

| Route | Page |
| ----- | ---- |
| `/login` | sign in, first-run setup |
| `/welcome` | create a first project |
| `/p/[project]` | overview: quality trend per dataset, collections, traffic, recent activity |
| `/p/[project]/collections` | collections |
| `/p/[project]/collections/[collection]` | documents with per-version index status, add file, URL or text |
| `.../documents/[document]` | parsed sections and metadata, chunks per version |
| `.../pipelines` | versions, active marker, index status, create and activate |
| `.../pipelines/new` | version editor with a live chunking preview |
| `.../pipelines/[version]` | configuration, build progress, chunk browser with size distribution |
| `/p/[project]/playground` | query one version or two side by side, with per-stage scores and the cited answer; the request lives in the URL, so a result can be shared and reloaded |
| `/p/[project]/evaluations` | runs and datasets |
| `/p/[project]/evaluations/runs/[run]` | metrics, per-tag breakdown, per-question results |
| `/p/[project]/evaluations/compare?runs=a,b` | side-by-side metrics, chart, configuration diff, per-question deltas |
| `/p/[project]/evaluations/datasets/[dataset]` | items, JSONL import and export, run history, gate thresholds |
| `/p/[project]/analytics` | requests per day, latency, zero-hit rate, top queries, per collection |
| `/p/[project]/settings` | general, members, API keys with SDK snippets, activity |

Every colour comes from CSS tokens with light and dark palettes; the theme is applied before
first paint.
