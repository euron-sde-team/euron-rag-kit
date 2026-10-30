# Configuration

Every setting RAGKit reads, where it comes from, and what changes on AWS. The API and the
worker read the same environment variables (validated at startup by
`apps/api/src/ragkit_server/core/config.py`; an invalid value stops the process with a clear
message). The web app reads two variables at runtime. The SDK and CLI read three.

- [How configuration is supplied](#how-configuration-is-supplied)
- [API and worker](#api-and-worker)
- [Web app](#web-app)
- [SDK and CLI](#sdk-and-cli)
- [Local compose variables](#local-compose-variables)
- [Pipeline configuration](#pipeline-configuration)
- [Model providers](#model-providers)

## How configuration is supplied

| Where | Source |
| ----- | ------ |
| `make up` (local) | `deploy/compose/compose.yaml` and `compose.floci.yaml`, with secrets from `deploy/compose/.env` (written once by `make env` with random values) |
| `make up-aws` | the same, plus `deploy/compose/.env.aws` with real resource names |
| AWS (ECS) | `infra/terraform/modules/deployment`: plain values in the task definitions, secrets injected from Secrets Manager |
| Running the API by hand | your shell environment; every setting has a development default |

## API and worker

### Application

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `APP_ENV` | `development` | `production` turns on the startup guard rails (see [security](../architecture/security.md#production-guard-rails)) and HSTS |
| `PRODUCT_NAME` | `Euron RAGKit` | shown in the API docs |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `LOG_FORMAT` | `json` | `console` for coloured local logs |
| `WEB_URL` | `http://localhost:3160` | allowed origin for cookie requests |
| `API_URL` | `http://localhost:8160` | used in printed links |
| `CORS_ORIGINS` | `http://localhost:3160,http://127.0.0.1:3160` | comma-separated web origins; `*` is refused in production |
| `ALLOW_SIGNUP` | `false` | let anyone create an account from the sign-in page |

### Database and cache

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `DATABASE_URL` | `postgresql+asyncpg://ragkit:ragkit@localhost:5456/ragkit` | Postgres 16 with pgvector 0.8 |
| `DATABASE_SECRET_ARN` | unset | on AWS: the RDS-managed secret; the password is read from it for each new connection, so rotation needs no restart |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | `10`, `10` | per process |
| `MIGRATE_ON_BOOT` | `false` | apply migrations at startup under an advisory lock (compose and AWS set `true`) |
| `REDIS_URL` | `redis://localhost:6416/0` | Valkey or Redis |

### Sessions and keys

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `SESSION_SECRET` | development value | signs session tokens; 32+ random characters in production |
| `API_KEY_PEPPER` | development value | keys API key hashes; must differ from `SESSION_SECRET` |
| `SESSION_TTL_HOURS` | `168` | |
| `COOKIE_SECURE` | `false` | `true` behind HTTPS (required in production) |
| `COOKIE_DOMAIN` | unset | set when the web app and API share a parent domain |

### Storage and the job queue

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `STORAGE_BACKEND` | `local` | `s3` locally on Floci and on AWS |
| `STORAGE_DIR` | `data/files` | for `local` |
| `S3_BUCKET`, `S3_KMS_KEY_ID` | unset | bucket and KMS key (alias or ARN) for SSE-KMS |
| `AWS_REGION` | `us-east-1` | |
| `AWS_ENDPOINT_URL` | unset | the emulator (`http://floci:4566` in compose); must be unset in production |
| `QUEUE_BACKEND` | `inline` | `sqs` to run jobs on the worker; `inline` runs them inside the API |
| `SQS_QUEUE_URL` | unset | the jobs queue |
| `WORKER_CONCURRENCY` | `2` | jobs one worker process runs at once |
| `WORKER_METRICS_PORT` | unset | the worker serves Prometheus metrics on this port (compose and AWS use `9160`) |
| `JOB_TIMEOUT_S` | `900` | |
| `STALE_JOB_MINUTES` | `15` | after this the reaper re-enqueues unfinished work |

### Ingestion

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `MAX_UPLOAD_MB` | `25` | per file, also the URL download cap |
| `MAX_DOCUMENT_PAGES` | `2000` | |
| `URL_FETCH_ALLOW_PRIVATE` | `false` | allow URL sources on private addresses; development only |
| `URL_FETCH_TIMEOUT_S` | `20` | |
| `TOKENIZER` | `tiktoken` | `heuristic` counts four characters per token |

### Embeddings, reranking and serving

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `DEFAULT_EMBEDDING_MODEL` | `bge-small-en-v1.5` | for collections created without a configuration |
| `EMBEDDINGS_CACHE_DIR` | image: `/app/models/fastembed` | where local models live (baked into the image) |
| `EMBEDDINGS_BATCH_SIZE` | `64` | |
| `EMBEDDINGS_API_BASE`, `EMBEDDINGS_API_KEY` | OpenAI, unset | for `openai:` embedding models |
| `EMBEDDING_CACHE_TTL_S` | 30 days | Valkey cache of embeddings by text hash |
| `RERANKER_MODEL` | `Xenova/ms-marco-MiniLM-L-6-v2` | cross-encoder, baked into the image |
| `QUERY_CACHE_TTL_S` | `300` | retrieval result cache; `0` turns it off |
| `QUERY_LOG_TEXT` | `true` | keep query text for the top-queries view |
| `WARM_MODELS` | `true` | load models at startup instead of on the first request |

### Answers and grading

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `LLM_PROVIDER` | `none` | `none` (offline extractive answers), `openai` (any OpenAI-compatible API) or `ollama` |
| `LLM_MODEL` | unset | required with a provider |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `LLM_API_KEY` | unset | |
| `OLLAMA_URL` | `http://localhost:11434` | compose uses `http://host.docker.internal:11434` |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT_S` | `0`, `600`, `90` | |
| `JUDGE_MODEL` | `LLM_MODEL` | model used by `grader: model` evaluation runs |

### Rate limits (per minute)

| Variable | Default |
| -------- | ------- |
| `RATE_LIMIT_LOGIN` | `10` per client address |
| `RATE_LIMIT_QUERY` | `600` per person or key (query and answer) |
| `RATE_LIMIT_INGEST` | `120` |
| `RATE_LIMIT_EVAL` | `30` |

### Process

| Variable | Notes |
| -------- | ----- |
| `FORWARDED_ALLOW_IPS` | peers trusted to set `X-Forwarded-For` (uvicorn); `127.0.0.1` in the image, the VPC range on AWS; never `*` |
| `DEMO_PASSWORD` | password for the demo accounts (`make demo` passes it from `.env`) |

## Web app

| Variable | Default | Notes |
| -------- | ------- | ----- |
| `API_URL` | `http://localhost:8160` | the API address **as the browser sees it** |
| `PRODUCT_NAME` | `Euron RAGKit` | |

Both are read at request time by the `/env.js` route, so one image serves every environment.

## SDK and CLI

| Variable | Notes |
| -------- | ----- |
| `RAGKIT_URL` | API base URL (default `http://localhost:8160`) |
| `RAGKIT_API_KEY` | a project API key (`rgk_...`) |
| `RAGKIT_PROJECT` | project slug |

## Local compose variables

`deploy/compose/.env` (from `make env`) holds `RAGKIT_SESSION_SECRET`,
`RAGKIT_API_KEY_PEPPER` and `RAGKIT_DEMO_PASSWORD`. Optional overrides, see
`deploy/compose/.env.example`:

| Variable | Default |
| -------- | ------- |
| `RAGKIT_WEB_PORT`, `RAGKIT_API_PORT` | `3160`, `8160` |
| `RAGKIT_PG_PORT`, `RAGKIT_REDIS_PORT`, `RAGKIT_FLOCI_PORT` | `5456`, `6416`, `4616` |
| `RAGKIT_LLM_PROVIDER`, `RAGKIT_LLM_MODEL`, `RAGKIT_LLM_BASE_URL`, `RAGKIT_LLM_API_KEY`, `RAGKIT_OLLAMA_URL` | model answers and grading |
| `RAGKIT_URL_FETCH_ALLOW_PRIVATE` | `false` |
| `RAGKIT_LOG_LEVEL`, `RAGKIT_PRODUCT_NAME` | |

Every port binds to `127.0.0.1` only.

## Pipeline configuration

Pipeline versions carry their own configuration (cleaning, chunking, embedding, retrieval,
answer); see the [LLD](../architecture/LLD.md#pipeline-configuration) for every field. It is
set per collection in the dashboard, through `POST .../pipelines`, or with the SDK:

```python
docs.create_pipeline(
    "Smaller chunks",
    config={"chunking": {"strategy": "recursive", "chunk_tokens": 192, "overlap_tokens": 24}},
)
```

## Model providers

Local Ollama (no key, runs on your machine):

```bash
ollama pull llama3.2
echo 'RAGKIT_LLM_PROVIDER=ollama' >> deploy/compose/.env
echo 'RAGKIT_LLM_MODEL=llama3.2' >> deploy/compose/.env
make up
```

Any OpenAI-compatible API:

```bash
RAGKIT_LLM_PROVIDER=openai
RAGKIT_LLM_MODEL=gpt-4.1-mini
RAGKIT_LLM_BASE_URL=https://api.openai.com/v1
RAGKIT_LLM_API_KEY=...
```

With a provider configured, pipeline versions can use the `openai` or `ollama` answerer and
evaluation runs can use `grader: model`. Without one, both stay disabled in the dashboard and
everything else works.
