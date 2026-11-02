<p align="center">
  <img src="docs/assets/banner.svg" alt="Euron RAGKit: build, measure and serve retrieval pipelines, with versioned configurations, a playground that shows every stage's score and evaluations compared across versions" width="100%">
</p>

<p align="center">
  <img alt="Open source" src="https://img.shields.io/badge/open_source-%E2%9D%A4-0f766e?style=flat">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22c55e?style=flat"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776ab?style=flat&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.161-009688?style=flat&logo=fastapi&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat&logo=nextdotjs&logoColor=white">
  <img alt="PostgreSQL 16 with pgvector" src="https://img.shields.io/badge/PostgreSQL_16-pgvector-4169e1?style=flat&logo=postgresql&logoColor=white">
  <img alt="Valkey 8" src="https://img.shields.io/badge/Valkey-8-dc382d?style=flat&logo=redis&logoColor=white">
  <img alt="Terraform" src="https://img.shields.io/badge/IaC-Terraform-7b42bc?style=flat&logo=terraform&logoColor=white">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-ready-ff9900?style=flat&logo=amazonwebservices&logoColor=white">
</p>

<p align="center">
  <a href="https://github.com/euron-sde-team/euron-rag-kit/stargazers"><img alt="Star this repo" src="https://img.shields.io/github/stars/euron-sde-team/euron-rag-kit?style=social&label=Star%20this%20repo"></a>
  <a href="https://github.com/euron-sde-team/euron-rag-kit/fork"><img alt="Fork" src="https://img.shields.io/github/forks/euron-sde-team/euron-rag-kit?style=social&label=Fork"></a>
  <a href="https://github.com/euron-sde-team/euron-rag-kit/watchers"><img alt="Watch" src="https://img.shields.io/github/watchers/euron-sde-team/euron-rag-kit?style=social&label=Watch"></a>
  <br>
  <a href="https://github.com/euron-sde-team/euron-rag-kit/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/euron-sde-team/euron-rag-kit?style=flat&color=0f766e"></a>
  <a href="https://github.com/euron-sde-team/euron-rag-kit/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-34d399?style=flat"></a>
  <a href="https://github.com/euron-sde-team/euron-rag-kit/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/euron-sde-team/euron-rag-kit?style=flat&color=8b95a8"></a>
  <img alt="Runs offline with no API key" src="https://img.shields.io/badge/runs_offline-no_API_key_needed-082a2b?style=flat">
</p>

<p align="center">
  <b><a href="#-quickstart">Quickstart</a></b> |
  <b><a href="#️-architecture">Architecture</a></b> |
  <b><a href="#-explore-the-repository">Explore the repo</a></b> |
  <b><a href="docs/api/openapi.json">API reference</a></b> |
  <b><a href="#️-deploy-to-aws">Deploy</a></b> |
  <b><a href="docs/architecture/security.md">Security</a></b> |
  <b><a href="#-documentation">Docs</a></b>
</p>

**Euron RAGKit** is an open-source, MIT-licensed toolkit for building, measuring and serving
retrieval-augmented generation (RAG), part of the open-source initiative of **ENGAGESPHERE
TECHNOLOGY PRIVATE LIMITED**. Point it at your content (PDF, Word, Markdown, HTML, text, CSV
and web pages), describe how it should be chunked, embedded, retrieved and reranked as a
versioned pipeline, watch what every stage did in the playground, score each version on your
own questions, and serve the winner through an API and a Python SDK.

It is not a chat app. It is for the engineer who owns a RAG feature and has to answer three
questions with evidence instead of intuition: which settings work best for our content, did
this change make retrieval better or worse (and on which questions), and can CI stop a
regression before it ships?

- Pipelines are versions: immutable, numbered configurations (cleaning, chunking, embedding,
  retrieval, reranking, answering). Versions that only change retrieval share an index, so
  trying a reranker costs no rebuild.
- Retrieval shows its work: every hit carries its vector, keyword, fused and rerank score and
  rank, and the time each stage took. Two versions run side by side.
- Answers can be checked: cited answers whose citations are verified against the passages the
  answerer was given, offline by default, with OpenAI-compatible and Ollama models behind the
  same interface.
- Evaluation is built in: datasets of questions with expected sources, deterministic metrics
  (hit rate, recall, precision, MRR, nDCG, faithfulness, answer relevance, correctness), runs
  compared across versions down to the question, and a CI gate that fails on regression.

The whole stack runs on a laptop with no API key and no cloud account (a bundled embedding
model and reranker, an extractive answerer, an AWS emulator), and deploys to AWS with one
command from the same Terraform.

<p align="center">
  <img src="docs/assets/tour.gif" alt="Product tour: sign-in, the overview with retrieval quality over time, documents, pipeline versions, a version's chunks, a new version with a live chunk preview, the playground with per-stage scores, a cited answer, two versions side by side, evaluation runs, a run, a comparison, analytics and API keys" width="100%">
</p>

> [!NOTE]
> Everything in the tour ran for real: Docker Compose on a laptop, with S3, SQS, KMS and
> Secrets Manager emulated locally and provisioned by the same Terraform modules that build
> production, every chunk embedded by the bundled model, and every metric computed by the
> worker. `make up && make demo` reproduces it.

---

## 📚 Table of contents

- [Why Euron RAGKit](#-why-euron-ragkit)
- [At a glance](#-at-a-glance)
- [Screenshots](#️-screenshots)
- [Features](#-features)
- [Architecture](#️-architecture)
  - [Life of a query](#life-of-a-query)
  - [Measuring a change](#measuring-a-change)
- [Tech stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Quickstart](#-quickstart)
- [Explore the repository](#-explore-the-repository)
- [API](#-api)
- [Configuration](#️-configuration)
- [Deploy to AWS](#️-deploy-to-aws)
- [Security model](#-security-model)
- [Testing](#-testing)
- [Documentation](#-documentation)
- [Roadmap](#️-roadmap)
- [FAQ](#-faq)
- [Contributing, security and license](#-contributing-security-and-license)

---

## 💡 Why Euron RAGKit

Most RAG demos stop at "it answers". Production RAG fails in quieter ways: a chunk size that
cuts a table from its header, a reranker that helps on average and hurts on identifiers, an
embedding upgrade that drops recall on exactly the questions your users ask. Frameworks give
you the parts; nothing tells you whether your pipeline got better. Euron RAGKit is the
workbench around the parts.

- **Change one thing at a time.** A pipeline version is immutable and numbered. Creating
  version N+1 tells you whether it reuses an existing index (only retrieval or answering
  changed) or builds a new one, and shows a live preview of how it chunks your own documents
  first.
- **See where a result came from.** The playground runs a query through any version and shows
  each stage: the embedding and the vector search, the keyword search, the fusion, the
  rerank, with every score, rank and timing. Put two versions side by side and see where
  their rankings differ.
- **Measure, do not guess.** Datasets hold your questions with the document and the evidence
  sentence that answers each. Runs score every question with deterministic metrics, so the
  same run gives the same numbers, and relevance is judged by evidence, not chunk ids, which
  is what makes different chunking strategies comparable.
- **Gate releases on it.** Mark a run as the baseline, and `ragkit eval gate` fails a CI job
  when a metric falls below its floor or drops against the baseline, with a Markdown report.
- **Serve what won.** Project API keys, a REST API, a typed Python SDK, Valkey caches, rate
  limits and per-project analytics.
- **Run it anywhere.** Postgres with pgvector is the only index store. Locally the stack runs
  on Docker with an AWS emulator and no key; on AWS the same Terraform provisions RDS,
  ElastiCache, S3, SQS, KMS and ECS.

## 📊 At a glance

| | |
| --- | --- |
| **Apps** | Web dashboard (collections, pipelines, playground, evaluations, analytics), API, job worker, operator CLI, Python SDK with the `ragkit` command |
| **Sources** | Uploads (PDF, Word, Markdown, HTML, text, CSV), URLs (snapshot kept) and raw text, with JSON metadata for filtering |
| **Pipeline** | 6 switchable cleaning rules, 3 chunkers (fixed windows, recursive by structure, sentence windows), 6 embedding models (2 bundled), 3 retrieval modes (vector, keyword, hybrid) with RRF or weighted fusion, 3 rerankers (none, lexical, cross-encoder), 3 answerers (extractive, OpenAI-compatible, Ollama) |
| **Evaluation** | 8 metrics (hit rate, context recall, context precision, MRR, nDCG, faithfulness, answer relevance, answer correctness), datasets as JSONL, runs compared side by side, baselines and a CI gate |
| **Demo** | Acme Payments: 20 documents in 2 collections, 3 pipeline versions, 3 datasets, 7 evaluation runs and 14 days of query traffic, all produced by the real pipeline |
| **Infrastructure** | 12 Terraform modules, 3 environments (local emulator, AWS dev, AWS prod) |
| **Tests** | 166 API unit, 14 SDK and 47 web unit, 60 integration (real PostgreSQL, Valkey and emulated AWS), 27 browser end-to-end, plus a QA crawl of every page at two viewports |
| **License** | MIT |

## 🖼️ Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/07-playground-stages.png" alt="The playground showing a hybrid query with the time per stage and the vector, keyword, fused and rerank score of each hit"><br><sub><b>Playground.</b> Every hit with its score and rank at each stage, and where the time went.</sub></td>
    <td width="50%"><img src="docs/assets/screenshots/12-compare.png" alt="A comparison of three evaluation runs with metric bars, deltas and the configuration differences"><br><sub><b>Compare runs.</b> Metric deltas, the settings that differ and the questions that improved or regressed.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/02-overview.png" alt="The project overview with retrieval quality across runs of the golden dataset, collections and recent activity"><br><sub><b>Overview.</b> Retrieval quality across runs, collections, traffic and recent activity.</sub></td>
    <td><img src="docs/assets/screenshots/04-pipelines.png" alt="The pipeline versions of a collection with the serving version, index status and chunk counts"><br><sub><b>Pipeline versions.</b> Which version serves, how it is built and whether its index is ready.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/06-new-version-preview.png" alt="A new pipeline version with a live chunking preview and a notice that the change builds a new index"><br><sub><b>New version.</b> A live preview of your own documents, and whether the change reuses an index.</sub></td>
    <td><img src="docs/assets/screenshots/05-version-chunks.png" alt="A pipeline version's chunks with the size distribution and an expanded sentence window"><br><sub><b>Chunks.</b> Browse what a version actually indexed, with sizes and context windows.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/08-playground-answer.png" alt="A cited answer with a citation open to show its supporting quote"><br><sub><b>Cited answers.</b> Citations verified against the passages given, each with its quote.</sub></td>
    <td><img src="docs/assets/screenshots/09-playground-compare.png" alt="Two pipeline versions side by side for one query, with rank changes between them"><br><sub><b>Side by side.</b> Two versions for one query, with where their rankings differ.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/10-evaluations.png" alt="The evaluation runs table with metrics per run and the baseline marked"><br><sub><b>Evaluations.</b> Every run with its metrics, ready to select and compare.</sub></td>
    <td><img src="docs/assets/screenshots/11-run.png" alt="An evaluation run with its metrics, the release gate verdict and per-question evidence"><br><sub><b>A run.</b> Metrics, the release gate verdict and each question's retrieved evidence.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/13-dataset.png" alt="A dataset with its questions, run history chart and gate thresholds"><br><sub><b>Datasets.</b> Questions with expected sources, run history and the gate thresholds.</sub></td>
    <td><img src="docs/assets/screenshots/03-documents.png" alt="The documents of a collection with their status and the index state per version"><br><sub><b>Documents.</b> PDF, Word, Markdown, HTML, CSV and text, with parse status per document.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/14-analytics.png" alt="Analytics with requests per day, latency percentiles, the zero-hit rate and top queries"><br><sub><b>Analytics.</b> Traffic, latency, the share of queries that found nothing and the top queries.</sub></td>
    <td><img src="docs/assets/screenshots/15-api-keys.png" alt="Project API keys with ready-to-run SDK, curl and CI gate snippets"><br><sub><b>API keys.</b> Viewer and editor keys, with SDK, curl and CI gate snippets.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/16-dark-compare.png" alt="A run comparison in the dark theme"><br><sub><b>Dark theme.</b> Follows the system setting, switchable from the account menu.</sub></td>
    <td><img src="docs/assets/screenshots/17-dark-playground.png" alt="The playground in the dark theme"><br><sub><b>Dark playground.</b> The same stages and scores, in the dark theme.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/assets/screenshots/01-sign-in.png" alt="The sign-in page"><br><sub><b>Sign in.</b> Sessions in an httpOnly cookie, a per-address sign-in limit.</sub></td>
    <td></td>
  </tr>
</table>

## ✨ Features

| Area | What you get |
| --- | --- |
| **Ingestion** | Uploads, URLs and raw text; the extension and the file's bytes must agree; archive guards; SHA-256 deduplication per collection; documents parsed once into sections and kept in S3, so any index can be rebuilt; an SSRF-guarded URL loader that stores a snapshot |
| **Cleaning and chunking** | Six switchable rules (Unicode normalisation, whitespace, boilerplate and duplicate removal, e-mail redaction, minimum block size); fixed windows as the baseline, recursive chunking that follows headings and never crosses a section, sentence windows that retrieve small and answer from a wider context |
| **Pipeline versions** | Immutable, numbered configurations with a name and a description; an index fingerprint so versions share an index when only retrieval or answering changed; a live chunk preview; activation as a separate, explicit step; every version's chunks browsable with a size histogram |
| **Embeddings** | A bundled ONNX model (`bge-small-en-v1.5`) and a deterministic hash embedder that need no download; local models fetched on first use; OpenAI-compatible and Ollama embeddings at 384, 768, 1024 or 1536 dimensions; contextual embedding of title and heading with the text |
| **Retrieval** | pgvector HNSW and Postgres full-text search, RRF or weighted fusion, JSON metadata filters compiled to parameterised SQL, a local cross-encoder reranker with a lexical fallback that says so, per-stage scores, ranks and timings in every response |
| **Answers** | An extractive answerer that works offline (numbers, table rows and "not found" handled), OpenAI-compatible and Ollama answerers, sources fenced as data against prompt injection, citations verified against the sources the answerer was given |
| **Evaluation** | Datasets with expected sources, evidence and reference answers, JSONL import and export; eight deterministic metrics and an optional model-graded mode; runs with a full configuration snapshot and per-question results; comparison of two to four runs with a configuration diff and improved or regressed questions; baselines; a regression gate |
| **Serving** | Project API keys with roles and expiry, a REST API, the Python SDK and CLI, Valkey caches for embeddings and results (retired when the corpus changes), rate limits, query analytics |
| **Dashboard** | Overview with quality trends, collections and documents, pipeline versions, the playground, evaluations and comparisons, datasets with gate thresholds, analytics, members, API keys, activity; light and dark themes; usable on a phone |
| **Operations** | Liveness and readiness probes, Prometheus metrics (stage latencies, cache hits, reranker fallbacks, jobs), JSON logs with request ids, an SQS worker with heartbeats, a stale-work reaper, a dead-letter queue and a graceful hand-back on deploys |

## 🏗️ Architecture

<p align="center">
  <img src="docs/assets/diagrams/architecture.svg" alt="Architecture: people and applications reach the web app and the API through one load balancer; the API answers queries from PostgreSQL with pgvector, caches in Valkey, stores originals in S3 and queues job ids on SQS; workers consume the queue, parse documents, build indexes and run evaluations; a model provider is optional" width="100%">
</p>

Three services run on ECS Fargate from two images; the web app and the API sit behind one
Application Load Balancer, and the worker has no inbound path at all:

- **web** (`app.<domain>`): the Next.js dashboard. One image for every environment; it reads
  the API address at run time from `/env.js`.
- **api** (`api.<domain>`): the FastAPI service: authentication, projects and keys, intake of
  documents, pipeline versions and their indexes, the query and answer endpoints, datasets,
  runs, comparisons and the gate, analytics. It applies migrations on boot under an advisory
  lock. The embedding model and the reranker are baked into its image.
- **worker**: the same image with another command. It consumes the jobs queue: parses each
  document once, builds an index entry per document and index (clean, chunk, embed), and
  scores evaluation runs. One elected worker also runs the stale-work reaper.

[HLD](docs/architecture/HLD.md) | [LLD](docs/architecture/LLD.md) | [Data model](docs/architecture/data-model.md) | [Decision records](docs/architecture/adr/README.md)

### Life of a query

```mermaid
sequenceDiagram
  autonumber
  participant C as Client (dashboard, SDK, API key)
  participant A as API
  participant V as Valkey
  participant P as PostgreSQL + pgvector
  participant R as Reranker
  participant M as Answerer
  C->>A: POST /collections/{c}/answer {query, overrides?, filters?}
  A->>A: authorise, rate limit, resolve the active version and its index
  A->>V: result cache lookup (key includes the corpus version)
  A->>V: embed the query (cached by text hash)
  par vector candidates
    A->>P: HNSW search over this index, with metadata filters
  and keyword candidates
    A->>P: full-text search over this index, same filters
  end
  A->>A: fuse the two lists (RRF or weighted)
  A->>R: rerank the top candidates (cross-encoder, or lexical fallback)
  A->>M: sources packed into the context budget
  M-->>A: answer with [n] markers
  A->>A: verify citations against the sources given
  A->>P: log the query for analytics
  A-->>C: answer, citations, hits with per-stage scores, timings
```

### Measuring a change

```mermaid
flowchart LR
  ds[Dataset: questions, expected sources, reference answers] --> r1[Run on version 2]
  ds --> r2[Run on version 3]
  r1 --> m1[Metrics per question and in aggregate]
  r2 --> m2[Metrics per question and in aggregate]
  m1 --> cmp[Compare: deltas, configuration diff, improved and regressed questions]
  m2 --> cmp
  m1 -- baseline --> gate{Gate: floors and largest drop}
  m2 --> gate
  gate -- pass --> ship[Activate the version]
  gate -- fail --> fix[Look at the regressed questions in the playground]
```

The API layers each have one job:

| Layer | Folder | Job |
| --- | --- | --- |
| Routes | `apps/api/src/ragkit_server/api/routes/` | URL, request and response models, the access dependency, nothing else |
| Services | `apps/api/src/ragkit_server/services/` | Business rules, transactions, cache invalidation, the audit trail |
| Repositories | `apps/api/src/ragkit_server/repositories/` | The only database access; every query is scoped to a project |
| Ingestion, retrieval, evaluation | `.../ingestion/`, `.../retrieval/`, `.../evaluation/` | Pure modules with no I/O: parsers and chunkers, fusion and filters and rerankers, relevance and metrics and the gate |
| AI | `apps/api/src/ragkit_server/ai/` | Embedding providers, answerers, citations, the model judge |

Read more: [security](docs/architecture/security.md) | [threat model](docs/architecture/threat-model.md)

## 🧰 Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic | Typed end to end; one package for the API, the worker and the CLI |
| Index store | PostgreSQL 16 with pgvector 0.8 (HNSW) and full-text search | Vectors, keywords and metadata filters in one transactional database ([ADR 0001](docs/architecture/adr/0001-postgres-and-pgvector-as-the-index.md)) |
| Versions | Immutable pipeline versions, indexes shared by fingerprint | Experiments you can trust and rebuilds you can avoid ([ADR 0002](docs/architecture/adr/0002-immutable-pipeline-versions-and-shared-indexes.md)) |
| Evaluation | Relevance by document and evidence, deterministic metrics | Comparable across chunking strategies, reproducible ([ADR 0003](docs/architecture/adr/0003-evidence-based-relevance.md)) |
| Models | ONNX embedding model and cross-encoder in the image; OpenAI-compatible and Ollama adapters | Works with no key; a hosted model is a setting ([ADR 0004](docs/architecture/adr/0004-deterministic-providers-first.md)) |
| Queue | SQS with a dead-letter queue | Parse, index and evaluation jobs survive duplicates, crashes and deploys ([ADR 0006](docs/architecture/adr/0006-one-queue-for-parse-index-and-eval-jobs.md)) |
| Coordination | Valkey (Redis-compatible) | Embedding and result caches, rate limits, revoked sessions, worker leader election |
| Web | Next.js 16, React 19, Tailwind 4, TanStack Query 5, Radix primitives, Recharts | A fast, accessible dashboard with one image for every environment |
| AWS | ECS Fargate (ARM64), ALB, WAF, RDS, ElastiCache, S3, SQS, KMS, Secrets Manager, CloudWatch | Managed building blocks, least-privilege roles |
| Infrastructure as code | Terraform | The same modules build AWS and the local emulator ([ADR 0005](docs/architecture/adr/0005-floci-for-local-aws.md)) |
| Tests | pytest, Vitest, Playwright with axe | Unit, integration against real PostgreSQL, Valkey and emulated AWS, browser end-to-end and QA |

## 📋 Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| [Docker](https://docs.docker.com/get-docker/) with Compose v2 | 24+ | The local stack (give it 6 GB of memory: the API and the worker each load an embedding model and a reranker) |
| [uv](https://docs.astral.sh/uv/) | 0.13+ | The API's Python environment, outside Docker |
| [Node.js](https://nodejs.org/) | 22 LTS | The web app and the browser tests, outside Docker |
| [pnpm](https://pnpm.io/) | 9 (`corepack enable`) | The JavaScript workspace |
| [Terraform](https://developer.hashicorp.com/terraform/install) | 1.10+ | Only for deploying to AWS (local runs use a pinned container) |
| [AWS CLI](https://aws.amazon.com/cli/) | 2 | Only for deploying to AWS |

Free local ports (each overridable in `deploy/compose/.env`): 3160 (web), 8160 (API), 5456
(PostgreSQL), 6416 (Valkey), 4616 (AWS emulator).

## 🚀 Quickstart

```bash
git clone https://github.com/euron-sde-team/euron-rag-kit.git
cd euron-rag-kit
make up      # build and start everything; Terraform provisions the AWS emulator first
make demo    # three people, a project with two collections, versions, datasets and runs
```

| Open | As |
| --- | --- |
| http://localhost:3160 | `priya.raman@acme-payments.example` (owner of Acme Payments), `daniel.okafor@acme-payments.example` (editor) or `sofia.lindqvist@acme-payments.example` (viewer) |
| http://localhost:8160/docs | The interactive API reference |

The password for every demo account is printed by `make demo` (it is generated by `make env`
and stored in `deploy/compose/.env`), along with a viewer API key and an editor key and a
`curl` line to try. Then:

1. Open **Playground**, pick **Developer docs** and ask `how do I verify webhook signatures`:
   every hit shows its vector, keyword, fused and rerank score. Switch on **Write a cited
   answer**, or **Compare with** another version.
2. Open **Collections, Developer docs, Pipelines, New version**, change the chunk size, and
   watch the preview and the "builds a new index" notice.
3. Open **Evaluations**, tick the v1 and v2 runs on the support golden set and press
   **Compare**.
4. Add your own content with **Add sources**, write a dataset of real questions, run it,
   change one setting in a new version, run again, compare.

```bash
pip install ./sdk/python
export RAGKIT_URL=http://localhost:8160 RAGKIT_PROJECT=acme-payments RAGKIT_API_KEY=rgk_...
ragkit answer developer-docs "What is the request rate limit in live mode?"
```

`make down` stops everything and deletes the data. To answer with a model instead of the
offline extractive answerer, set `RAGKIT_LLM_PROVIDER=ollama` (or `openai` with
`RAGKIT_LLM_API_KEY`) and `RAGKIT_LLM_MODEL` in `deploy/compose/.env`, then `make up`.

[Full local guide](docs/guides/quickstart-local.md) |
[Guided walkthrough](docs/guides/walkthrough.md) |
[Troubleshooting](docs/guides/troubleshooting.md)

## 🧭 Explore the repository

```text
euron-rag-kit/
├── apps/
│   ├── api/                     FastAPI service, job worker and CLI (one package, one image)
│   │   ├── src/ragkit_server/
│   │   │   ├── api/                 routes and request dependencies
│   │   │   ├── services/            business rules: intake, pipelines, retrieval, evaluation, analytics
│   │   │   ├── repositories/        all database access, scoped to a project
│   │   │   ├── ingestion/           sniffing, parsers, cleaning rules, the three chunkers
│   │   │   ├── retrieval/           fusion, metadata filters, rerankers, context packing
│   │   │   ├── ai/                  embeddings, answerers, citations, the model judge
│   │   │   ├── evaluation/          relevance, metrics, aggregation, comparison, the gate
│   │   │   ├── integrations/        S3, SQS, the SSRF-guarded URL fetcher
│   │   │   ├── demo/                the demo seed
│   │   │   ├── models/ schemas/     tables and API shapes
│   │   │   ├── db/ migrations/      engine, sessions, advisory-locked migrations
│   │   │   ├── core/                config, errors, logging, security, rate limits, metrics
│   │   │   ├── worker.py            the SQS job worker
│   │   │   └── cli.py               migrate, users, demo seed, reindex, OpenAPI export
│   │   └── tests/                   unit and integration suites
│   └── web/                     Next.js dashboard
├── sdk/python/                  the euron-ragkit package and the ragkit command
├── samples/                     the demo corpus and evaluation datasets
├── infra/
│   ├── terraform/               modules + envs (local-floci, aws-dev, aws-prod)
│   └── docker/                  api and web images
├── deploy/compose/              the local stack (Floci or real AWS overlay)
├── e2e/                         Playwright: journeys, the QA crawl, screenshots and the tour
├── docs/                        architecture, ADRs, guides, OpenAPI
└── scripts/                     deploy, one-off tasks, local env, test services, sanitization
```

**Where to start reading:**

| To understand | Read |
| --- | --- |
| How a query is answered | `services/retrieval.py`, then `retrieval/fusion.py`, `retrieval/rerankers.py` and `repositories/chunks.py` |
| How a document becomes chunks | `services/ingestion.py`, then `ingestion/chunkers.py` and `ingestion/cleaning.py` |
| Why two versions share an index | `schemas/pipeline.py` (`fingerprint`), then `services/pipelines.py` |
| How answers are cited | `ai/extractive.py`, `ai/citations.py` |
| How a metric is computed | `evaluation/relevance.py`, then `evaluation/metrics.py` and `tests/unit/test_metrics.py` |
| How the gate decides | `evaluation/gate.py`, then `sdk/python/src/ragkit/gate.py` |
| How jobs survive crashes | `worker.py`, then `services/ingestion.py` (`reap_stale`) and `tests/integration/test_worker.py` |
| How projects are isolated | `api/deps.py` and `repositories/`, then `tests/integration/test_access.py` |
| How it deploys | `infra/terraform/modules/deployment/main.tf`, then `scripts/aws-deploy.sh` |

Paths in the second column are under `apps/api/src/ragkit_server/` unless they start with
`tests/`, `sdk/`, `infra/` or `scripts/`. The [walkthrough](docs/guides/walkthrough.md) tours
every screen with the demo data.

## 🔌 API

The [OpenAPI reference](docs/api/openapi.json) is exported from the application itself
(`make openapi`), so it always matches the code, and the running API serves it interactively
at `/docs`. Query a collection with a project API key:

```bash
curl -s -X POST "localhost:8160/api/v1/projects/acme-payments/collections/developer-docs/answer" \
  -H "authorization: Bearer $RAGKIT_API_KEY" -H 'content-type: application/json' \
  -d '{"query": "How do I rotate API keys without downtime?"}' | jq '.answer, .citations[].document_title'
```

Or from Python, and gate a pull request on the result:

```python
from ragkit import RAGKit

rk = RAGKit()  # RAGKIT_URL, RAGKIT_API_KEY and RAGKIT_PROJECT
hits = rk.collection("developer-docs").query("instant payout fee", top_k=3, rerank="cross-encoder").hits
run = rk.evals.run("support-golden", pipeline_version=3)   # waits for the worker
print(run.means["hit_rate"], run.means["mrr"])
```

```bash
ragkit eval gate support-golden --version 3 --min hit_rate=0.85 --max-drop 0.02 --report gate.md
# exit 0: passed, 1: a metric regressed, 2: the run could not be evaluated
```

Errors always have the shape `{"error": {"code", "message", "request_id"}}` and every response
carries an `X-Request-Id` header. The [API guide](docs/api/README.md) covers authentication,
retrieval overrides and filters, ingestion, pipeline versions and the evaluation workflow; the
[SDK README](sdk/python/README.md) covers the client and the command line.

## ⚙️ Configuration

The API and the worker read their configuration from the environment. With
`APP_ENV=production` they refuse to boot, listing every problem at once, unless:

- the session secret and the API key pepper are random, at least 32 characters and different
- cookies are secure and CORS names the web app's origins
- files go to S3 and jobs go through SQS, with no emulator endpoint
- URL sources cannot reach private addresses, and a configured model provider names its model

The web app reads `API_URL` and `PRODUCT_NAME` at run time from `/env.js`, so one image serves
every environment. Every variable, including the model providers, is documented in the
[configuration reference](docs/guides/configuration.md).

## ☁️ Deploy to AWS

```bash
cp infra/terraform/envs/aws-dev/terraform.tfvars.example infra/terraform/envs/aws-dev/terraform.tfvars
# set name_prefix, domain and route53_zone_id

make aws-deploy ENV=aws-dev       # registries, images, infrastructure, rollout
make aws-cli ENV=aws-dev ARGS="user create --email you@example.com --name 'You' --admin"
```

`aws-deploy` runs four steps:

1. Create the image registries.
2. Build and push the API and web images for ARM64, tagged with the git commit.
3. Apply the rest of the infrastructure.
4. Wait for the API, worker and web services to stabilise.

Migrations run on boot, under an advisory lock, and the first one enables pgvector. The
database password never appears in a task definition: the API and the worker read it from the
RDS-managed secret for each new connection, so a rotation needs no redeploy. Workers hand
their unfinished jobs back to the queue within the two minutes ECS gives them on every deploy.

| | aws-dev | aws-prod |
| --- | --- | --- |
| Availability zones | 2, one NAT | 3, NAT per zone, VPC interface endpoints |
| Database | single-AZ, 3-day backups | Multi-AZ, 14-day backups, deletion protection |
| Cache | one Valkey node | primary and replica |
| Edge | load balancer | load balancer with AWS WAF managed rules and rate limiting |
| API, worker, web | 1 to 2 tasks each | 2 to 6, 2 to 8 and 2 to 6 tasks |
| Logs | 14 days | 365 days, KMS-encrypted |

[Deployment guide](docs/guides/deploy-aws.md) | [Operations](docs/guides/operations.md)

## 🔐 Security model

| Concern | How it is handled |
| --- | --- |
| Project isolation | Every query is scoped to the caller's project; non-members get 404, not 403; an integration sweep calls every project route as an outsider and with another project's ids |
| Sessions | Argon2id passwords, a per-address sign-in limit that fails closed, signed sessions with a per-user version (a password change signs out every other session) and a revocation list for sign-out |
| Cookies and CSRF | HttpOnly, SameSite=Lax cookies; any write with a cookie must come from the web app's origin |
| API keys | `rgk_` keys scoped to one project and a viewer or editor role, shown once, stored as a peppered HMAC, expiring and revocable |
| Uploads | The extension picks the parser and the file's bytes must agree; size, page and archive-expansion limits; objects stored under generated keys, never user paths |
| URL sources | `http` and `https` only, DNS resolved and every address checked (no private, loopback, link-local or metadata ranges), redirects re-checked, size and time limits |
| Prompt injection | Retrieved text reaches a model fenced as numbered data with an instruction that it is not instructions; citations are verified against the sources given, and markers pointing elsewhere are removed |
| Queries | Metadata filters compile to parameterised SQL with validated field names; no request supplies SQL |
| Data at rest | S3, SQS, RDS, Valkey, Secrets Manager and logs encrypted with one customer-managed KMS key; TLS everywhere on AWS |
| Infrastructure | Private subnets, least-privilege task roles, `/metrics` closed at the load balancer, checkov with justified exceptions only |

Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).

## 🧪 Testing

| Suite | What it proves | Run |
| --- | --- | --- |
| API unit (166) | Parsers and sniffing, cleaning, the three chunkers, embeddings, fusion, metadata filters and their injection attempts, rerankers, the extractive answerer and citations, every metric on hand-computed cases, comparison and the gate, the URL guards, passwords, sessions and API keys, configuration guard rails | `make test` |
| SDK (14) and web unit (47) | Request shapes, retries and exit codes; the dashboard's helpers for drafts, runs, metrics, citations and snippets | `make test` |
| Integration (60) | The real API and worker against PostgreSQL with pgvector, Valkey and the AWS emulator: every format ingested, versions that share and build indexes, every retrieval stage and mode, cited answers, evaluation runs, comparisons and the gate, the worker over SQS including crashes and hand-backs, an isolation sweep, the SDK against a live server | `make test-integration` |
| Browser (27) | Sign-in and roles, collections and documents, pipeline versions, the playground, cited answers and side-by-side comparison, evaluation runs scored by the worker, comparisons, analytics, API keys, a password change | `make e2e` |
| QA crawl (4) | Every page at desktop and mobile widths: no console errors, failed requests, sideways scrolling, broken links or serious accessibility violations | `make qa` |
| Infrastructure | `terraform validate` (3 environments), tflint, checkov | `make tf-validate tf-lint tf-security` |

The API suites cover 80% of the `ragkit_server` package, branches included.
[Testing guide](docs/guides/testing.md)

## 📖 Documentation

| Architecture | Guides |
| --- | --- |
| [High-level design](docs/architecture/HLD.md) | [Quickstart (local)](docs/guides/quickstart-local.md) |
| [Low-level design](docs/architecture/LLD.md) | [Guided walkthrough](docs/guides/walkthrough.md) |
| [Data model](docs/architecture/data-model.md) | [Configuration reference](docs/guides/configuration.md) |
| [Security](docs/architecture/security.md) | [Deploy to AWS](docs/guides/deploy-aws.md) |
| [Threat model](docs/architecture/threat-model.md) | [Operations](docs/guides/operations.md) |
| [Decision records](docs/architecture/adr/README.md) | [Testing](docs/guides/testing.md) |
| [API reference (OpenAPI)](docs/api/openapi.json) / [API guide](docs/api/README.md) | [Troubleshooting](docs/guides/troubleshooting.md) |

## 🗺️ Roadmap

- Synthetic question generation from a corpus, to bootstrap a dataset
- Scheduled evaluation runs with notifications (e-mail, Slack, webhooks) when a gate fails
- Query rewriting and multi-query retrieval as pipeline stages that can be measured
- Streaming answers
- Per-document access control, so one collection can serve people with different rights
- Single sign-on (OIDC, SAML) and two-factor authentication for people
- OpenTelemetry traces across the API, the worker and model calls

Have an idea? [Open a feature request](https://github.com/euron-sde-team/euron-rag-kit/issues/new/choose).

## ❓ FAQ

<details>
<summary><b>Do I need an OpenAI key or a GPU?</b></summary>

No. The embedding model and the cross-encoder reranker are small ONNX models that run on a
CPU and ship in the image, and the extractive answerer composes cited answers from the
retrieved passages with no model at all. Evaluation metrics are deterministic. Point the
answerer (and, if you like, the grader) at any OpenAI-compatible API or at Ollama when you
want a model to write the answer; retrieval works exactly the same.
</details>

<details>
<summary><b>How is this different from a RAG framework or a chat-with-your-documents app?</b></summary>

A framework gives you the parts to assemble a pipeline in code, and a document-chat app gives
you one pipeline behind a chat box. RAGKit is the layer in between that neither provides:
versioned pipeline configurations, a view into every retrieval stage, and evaluation that
tells you whether version 3 is better than version 2 on your questions, with a CI gate. You
keep your application code; it calls the API or the SDK.
</details>

<details>
<summary><b>Why Postgres and pgvector instead of a vector database?</b></summary>

One transactional store keeps vectors, full-text indexes, metadata filters and the rest of
your data together, so a document delete, a metadata change or a version switch is one
consistent operation, and there is one thing to back up and run. HNSW indexes (partial per
embedding width) and pgvector's iterative scans keep filtered queries fast at the scale a
single collection reaches. The reasoning is in [ADR 0001](docs/architecture/adr/0001-postgres-and-pgvector-as-the-index.md).
</details>

<details>
<summary><b>How do you compare chunking strategies if chunks differ between versions?</b></summary>

Relevance is judged by evidence, not by chunk ids. A retrieved chunk counts as relevant when
it belongs to an expected document and contains the evidence sentence (after normalising case
and punctuation, or at least 80% of its content words). Fixed windows, structure-aware chunks
and sentence windows are therefore scored on the same scale. See
[ADR 0003](docs/architecture/adr/0003-evidence-based-relevance.md).
</details>

<details>
<summary><b>Are the metrics model-graded?</b></summary>

By default no: hit rate, recall, precision, MRR and nDCG come from the retrieved text, and
faithfulness, answer relevance and correctness are computed from the answer, its sources and
the pipeline's own embedder, so a run gives the same numbers every time and a gate does not
flake. A `grader: model` run asks the configured judge model instead and falls back to the
deterministic grade for an item whose reply cannot be parsed, recording that it did.
</details>

<details>
<summary><b>What happens if a worker dies in the middle of a job?</b></summary>

The queue message becomes visible again and another worker picks the job up; parse, index and
evaluation jobs are idempotent, and an evaluation run resumes from the questions it already
scored. After three failed receives SQS moves the message to the dead-letter queue and the row
is marked failed with the reason. A reaper re-sends work whose message was lost. A stopping
worker hands its unfinished jobs back at once.
</details>

<details>
<summary><b>Can it run outside AWS?</b></summary>

Yes. Locally it runs on PostgreSQL, Valkey and the Floci emulator in Docker Compose, and the
API also supports local disk storage and an inline job queue for development. The Terraform
targets AWS.
</details>

## 🤝 Contributing, security and license

Contributions are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in
[SECURITY.md](SECURITY.md). Notable changes are listed in the [changelog](CHANGELOG.md).

Released under the [MIT License](LICENSE). Copyright (c) 2026 ENGAGESPHERE TECHNOLOGY
PRIVATE LIMITED and the Euron RAGKit contributors.

<p align="center">
  If Euron RAGKit saves you time, <b><a href="https://github.com/euron-sde-team/euron-rag-kit/stargazers">⭐ star the repository</a></b>.
</p>
