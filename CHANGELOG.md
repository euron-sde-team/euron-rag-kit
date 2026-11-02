# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-02

First public release.

### Added

- Collections and ingestion: uploads (PDF, Word, Markdown, HTML, text, CSV), URLs and raw text
  with JSON metadata. The extension and the file's bytes must agree, archives are guarded
  against expansion, files are deduplicated by SHA-256, documents are parsed once into
  sections and the originals are kept in S3, so any index can be rebuilt. URLs are fetched by
  an SSRF-guarded loader that keeps a snapshot.
- Immutable, numbered pipeline versions: six switchable cleaning rules, three chunkers (fixed
  windows as the baseline, recursive by structure, sentence windows that retrieve small and
  answer from a wider context), the embedding model, retrieval defaults and the answerer. A
  fingerprint of the index settings lets versions that only change retrieval or answering
  share an index, activation is a separate step, and a live preview chunks your own documents
  with a draft before anything is built.
- Hybrid retrieval in PostgreSQL: pgvector HNSW indexes (partial per embedding width: 384,
  768, 1024 and 1536) with iterative scans, full-text search, reciprocal rank fusion and
  weighted fusion, JSON metadata filters compiled to parameterised SQL, a local cross-encoder
  reranker with a lexical fallback that the response reports, and per-stage scores, ranks and
  timings on every hit.
- Embeddings behind one interface: a bundled ONNX model (`bge-small-en-v1.5`) and a
  deterministic hash embedder, local models fetched on first use, OpenAI-compatible and Ollama
  embeddings, contextual embedding of title and heading, and a Valkey cache by text hash.
- Answers with citations: an extractive answerer that works offline (numbers, table rows and
  "not found" handled), OpenAI-compatible and Ollama answerers, retrieved text fenced as data
  against prompt injection, and citations verified against the sources the answerer was given.
- Evaluation: datasets of questions with expected sources, evidence and reference answers
  (JSONL import and export); relevance judged by document and evidence, so chunking strategies
  compare on one scale; eight deterministic metrics (hit rate, context recall, context
  precision, MRR, nDCG, faithfulness, answer relevance, answer correctness) and an optional
  model-graded mode; runs with a full configuration snapshot and per-question results;
  comparison of two to four runs with a configuration diff and improved or regressed
  questions; baselines; and a regression gate with floors and a largest allowed drop.
- Serving: project API keys with viewer and editor roles and expiry, a REST API with one error
  envelope and a request id on every response, a typed Python SDK (`euron-ragkit`) and the
  `ragkit` command line, including `ragkit eval gate` for CI (exit 0 pass, 1 regression, 2 not
  evaluated, Markdown or JSON report), result and embedding caches, rate limits and query
  analytics.
- A web dashboard: project overview with quality trends, collections and documents, pipeline
  versions with chunk browsing, the retrieval playground (stage scores, cited answers, two
  versions side by side, overrides and filters), evaluation runs, comparisons, datasets with
  gate thresholds, analytics, members, API keys with ready-to-run snippets, an activity trail,
  a change-password dialog, light and dark themes, and phone layouts.
- A job worker on SQS with a dead-letter queue: idempotent parse, index and evaluation jobs,
  visibility heartbeats, growing back-off, a leader-elected reaper for stale work, duplicate
  delivery handling and a graceful hand-back of unfinished jobs on shutdown.
- Operations: liveness and readiness probes, Prometheus metrics (stage latencies, cache hits,
  reranker fallbacks, documents and index entries, evaluation runs), JSON logs with request
  ids, advisory-locked migrations on boot, and production guard rails that refuse to start
  with unsafe settings.
- The `ragkit-server` operator CLI: migrate, create users (with a generated temporary password
  when nobody can be asked, as in an ECS one-off task), seed the demo, reindex and export the
  OpenAPI document.
- `make demo`: Acme Payments, a fictional payments company with 20 documents in two
  collections, three pipeline versions, three datasets, seven evaluation runs and two weeks of
  query traffic, all produced by the real pipeline.
- Docker images for the API (also the worker) and the web app; Docker Compose for the local
  stack on the Floci AWS emulator, provisioned by the same Terraform modules as AWS; Terraform
  environments `local-floci`, `aws-dev` and `aws-prod` (VPC, RDS PostgreSQL 16 with pgvector,
  ElastiCache Valkey, S3, SQS, KMS, ECS Fargate, ALB, WAF, alarms and a dashboard) with tflint
  and checkov clean.
- Tests: API unit and integration suites (real PostgreSQL with pgvector, Valkey and Floci),
  SDK and web unit tests, Playwright end-to-end tests, a QA crawl with axe at desktop and
  mobile widths, and README screenshots captured from the seeded stack.
- Documentation: high-level and low-level design, data model, security model, STRIDE threat
  model, six decision records, and guides for the local quickstart, configuration, deployment,
  operations, testing, troubleshooting and a walkthrough, plus the OpenAPI reference exported
  from the application.
