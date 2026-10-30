# Quickstart: run RAGKit locally

Everything runs in Docker on your machine: Postgres with pgvector, Valkey, the Floci AWS
emulator (S3, SQS, KMS, Secrets Manager), the API, the job worker and the web app. No cloud
account and no API key are needed.

- [Prerequisites](#prerequisites)
- [Start the stack](#start-the-stack)
- [Seed the demo project](#seed-the-demo-project)
- [Find your way around](#find-your-way-around)
- [Use your own content](#use-your-own-content)
- [Call it from code](#call-it-from-code)
- [Stop and reset](#stop-and-reset)
- [Run the API without Docker](#run-the-api-without-docker)

## Prerequisites

| Tool | Version | Used for |
| ---- | ------- | -------- |
| Docker with Compose v2 | 24+ | the whole stack (Docker Desktop, Colima or OrbStack) |
| GNU Make | any | the entry points |
| 6 GB of memory for Docker | | the API and the worker each load an embedding model and a reranker |

For development you will also want Python 3.12 with [uv](https://docs.astral.sh/uv/),
Node.js 22 with pnpm 9, and optionally Terraform 1.10+ (the Makefile falls back to a pinned
container).

## Start the stack

```bash
git clone https://github.com/euron-sde-team/euron-rag-kit.git
cd euron-rag-kit
make up
```

`make up` generates `deploy/compose/.env` with random local secrets (once), builds the API
and web images (the embedding model, the reranker and the tokenizer are baked in, so the
first build downloads about 200 MB), starts the data services, applies the local Terraform
environment to the emulator (KMS key, corpus bucket, jobs queue with a dead-letter queue,
secrets), then starts the API (which migrates the database), the worker and the web app. It
returns when every container is healthy.

| Service | Address |
| ------- | ------- |
| Dashboard | http://localhost:3160 |
| API and interactive reference | http://localhost:8160/docs |
| Postgres | `localhost:5456` (user, password and database `ragkit`) |
| Valkey | `localhost:6416` |
| Floci (AWS) | `http://localhost:4616` |

Ports are bound to `127.0.0.1` and can be changed in `deploy/compose/.env`
(`RAGKIT_WEB_PORT` and friends).

## Seed the demo project

```bash
make demo
```

The seeder creates **Acme Payments**, a fictional payments company with two collections:

- **Developer docs**: 16 documents (Markdown guides and reference, an HTML page, a CSV price
  list, release notes, a PDF service level agreement and a Word security overview) with
  three pipeline versions: a fixed-window vector baseline, the active structure-aware hybrid
  version with a cross-encoder, and a sentence-window experiment.
- **Support playbooks**: four playbooks added as text through the JSON loader.

It then imports three evaluation datasets (36, 8 and 6 questions), runs seven evaluations
(including two ablations of the active version), marks a baseline and replays two weeks of
query traffic through the real retrieval path. Every chunk, vector, score and metric is
computed by the pipeline; only the timestamps are spread over the past two weeks. It takes a
few minutes and prints the sign-ins:

| Account | Role |
| ------- | ---- |
| `priya.raman@acme-payments.example` | owner |
| `daniel.okafor@acme-payments.example` | editor |
| `sofia.lindqvist@acme-payments.example` | viewer |

The password is `RAGKIT_DEMO_PASSWORD` in `deploy/compose/.env`. The seeder also prints two
API keys (a viewer key for the "docs assistant" and an editor key for CI) and a `curl` line
to try.

## Find your way around

1. **Overview**: the retrieval quality trend of the golden dataset across runs, the
   collections, request volume and recent activity.
2. **Collections > Developer docs**: documents with their parse status; open one to see its
   parsed sections and the indexes it is in.
3. **Pipelines**: the three versions, which one is serving, and which share an index. Open
   v3 to browse its sentence-window chunks and their size histogram. **New version** shows a
   live chunking preview and tells you whether your change reuses an index.
4. **Playground**: ask `how do I verify webhook signatures`. Each hit shows its vector,
   keyword, fused and rerank scores and ranks; switch on "Write a cited answer", or compare
   v1 with v2 side by side.
5. **Evaluations**: tick the v1 and v2 runs on the golden set and press Compare: metric
   deltas, the configuration diff and the questions that improved or regressed. Open a run
   to see the release gate verdict and every question's retrieved evidence.
6. **Analytics** and **Settings > API keys** (with SDK, curl and CLI snippets).

The [walkthrough](walkthrough.md) follows one experiment end to end.

## Use your own content

1. Create a collection (the dashboard offers three starting configurations).
2. **Add sources**: upload files (PDF, Word, Markdown, HTML, text, CSV, up to 25 MB each),
   paste text, or list URLs. Optional JSON metadata becomes filterable on every chunk.
3. Watch documents move from queued to ready; the worker parses each once and indexes it into
   every version's index.
4. Write a dataset: a few dozen real questions with the document (by its id) and the sentence
   that answers each. Import it as JSONL from the Evaluations page.
5. Run it, change one setting in a new version, run again, compare.

## Call it from code

```bash
pip install ./sdk/python
export RAGKIT_URL=http://localhost:8160 RAGKIT_PROJECT=acme-payments RAGKIT_API_KEY=rgk_...
ragkit query developer-docs "how do I verify webhook signatures"
ragkit answer developer-docs "What is the rate limit in live mode?"
```

```python
from ragkit import RAGKit

rk = RAGKit()  # reads the three variables above
result = rk.collection("developer-docs").answer("How long do refunds take?")
print(result.answer)
```

## Stop and reset

```bash
make down    # stops everything and deletes the volumes: database, emulator, Terraform state
make up      # a clean stack again; then make demo
```

`make logs SERVICE=worker` follows one service; `make ps` shows their state.

## Run the API without Docker

For quick iteration on the API alone:

```bash
scripts/test-deps.sh                     # Postgres, Valkey and Floci from compose
cd apps/api
uv sync
MIGRATE_ON_BOOT=true uv run uvicorn ragkit_server.main:create_app --factory --port 8160 --reload
```

With the defaults the API stores files in `data/files` and runs jobs inline in its own process
(`STORAGE_BACKEND=local`, `QUEUE_BACKEND=inline`), so no worker is needed. Create an account
with `uv run ragkit-server user create --email you@example.com --name You --admin`, then run
the web app with `pnpm install && pnpm dev` from the repository root.
