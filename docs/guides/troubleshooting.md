# Troubleshooting

Symptoms, their usual cause, and the fix. Start with `make ps` and `make logs SERVICE=<name>`;
every API error carries a `request_id` you can search the logs for.

- [The local stack](#the-local-stack)
- [Documents and ingestion](#documents-and-ingestion)
- [Retrieval](#retrieval)
- [Answers](#answers)
- [Evaluation](#evaluation)
- [The API and the dashboard](#the-api-and-the-dashboard)
- [On AWS](#on-aws)

## The local stack

| Symptom | Cause | Fix |
| --- | --- | --- |
| `make up` fails with "port is already allocated" | Another program uses 3160, 8160, 5456, 6416 or 4616 | Move the port in `deploy/compose/.env` (`RAGKIT_WEB_PORT`, `RAGKIT_API_PORT`, `RAGKIT_PG_PORT`, `RAGKIT_REDIS_PORT`, `RAGKIT_FLOCI_PORT`) |
| `make up` stops at `terraform` | The emulator started slowly, or its state no longer matches the Terraform state (a half-removed stack) | `make down` (it removes both volumes together), then `make up`; `make logs SERVICE=terraform` shows the failing resource |
| The `terraform` container fails with `releases.hashicorp.com: unexpected EOF` | A network flake while it installs the AWS provider | Run `make up` again; the provider is cached in the stack's `tfdata` volume once it has downloaded |
| The first `make up` takes ten minutes or more | The image build downloads the embedding model, the reranker and the tokenizer (about 200 MB) and every Python and Node dependency | Later builds reuse the layers; the models are baked into the image, so nothing downloads at runtime |
| The API or the worker restarts or is `unhealthy` | Usually memory: each process loads an embedding model and a reranker, and Docker may have less than the 6 GB the stack wants | Give Docker 6 GB or more (`colima start --memory 6`), or set `WORKER_CONCURRENCY=1` |
| `Cannot connect to the Docker daemon` on macOS with Colima | Colima is stopped | `colima start` |
| The database refuses the migration with `extension "vector" is not available` | Postgres runs from a plain image without pgvector | Use the compose file's `pgvector/pgvector` image, or on RDS a PostgreSQL 16 minor version that ships pgvector |
| `make demo` prints "The demo project already exists; nothing to seed." | The demo accounts exist | `make down && make up && make demo` for a fresh stack |
| `make demo` takes several minutes | It really indexes the corpus into three pipeline versions, runs seven evaluations and replays two weeks of queries | Wait; `make logs SERVICE=worker` shows the work |
| `make e2e` fails at sign-in with 429 | More than ten sign-ins a minute from your address | Wait a minute; the suites reuse their saved sessions (`e2e/.auth/`) after the first sign-in |
| `make e2e` says "Set DEMO_PASSWORD" | `deploy/compose/.env` is missing | `make env`, then `make up && make demo` |
| `make test-integration` cannot connect | The test dependencies are not up | `scripts/test-deps.sh` starts Postgres, Valkey and Floci from the compose files; the suite uses its own `ragkit_test` database, Valkey database 15 and uniquely named buckets and queues |

## Documents and ingestion

| Symptom | Cause | Fix |
| --- | --- | --- |
| A document stays **queued** | No worker is running, or it cannot reach the queue | `make ps`, `make logs SERVICE=worker`. Without `QUEUE_BACKEND=sqs` the API runs jobs itself, so nothing is stuck unless the API is down |
| A document is **failed** with "This PDF is password-protected" | The file is encrypted | Remove the password and upload it again |
| ... "This file does not look like a PDF" (or Word, HTML, ...) | The extension and the file's bytes disagree (`content_mismatch`) | Save the file in the format its extension claims |
| ... "expands to more data than RAGKit processes safely" or "too many internal parts" | A Word document that unpacks far larger than it is (an archive guard) | Export it again from the source application |
| ... "No readable text was found. Scanned PDFs need OCR before they can be searched." | A scanned PDF with no text layer (a PDF with only some such pages is parsed and lists the skipped pages as a warning) | Run OCR first; RAGKit does not read images |
| ... "The page was empty." | A URL source that returned no text | Check the page renders without JavaScript; otherwise paste its text as a text source |
| An upload is rejected with `payload_too_large` | Above `MAX_UPLOAD_MB` (25) | Split the file or raise the limit; also see `MAX_DOCUMENT_PAGES` |
| An upload is reported as a duplicate | A file with the same bytes is already in the collection | Intended; change the file or delete the old document |
| `duplicate_external_id` | Two sources share an `external_id` | Give each source a distinct id; datasets refer to documents by it |
| A URL source fails with "The host ... could not be resolved" or a private-address refusal | The URL loader only fetches public `http` and `https` addresses (ports 80, 443 and 8000 to 9999), and re-checks every redirect | For a service on your own network, set `RAGKIT_URL_FETCH_ALLOW_PRIVATE=true` on a development stack only; production refuses it |
| ... "The server answered HTTP 403" | The site blocks automated fetches | Download the page and upload it, or add it as a text source |
| Tables in a PDF read as running text | PDFs store no table structure | Use the CSV, HTML or Word source of the table; CSV rows become `Column: value` records |

## Retrieval

| Symptom | Cause | Fix |
| --- | --- | --- |
| A query returns no hits | The version's index is still `building`, the collection has no active version (`no_active_version`), the filter excludes everything, or `keyword` mode got a query made only of stop words | Check the version's index progress, activate a version, loosen the filter, try `hybrid` |
| `index_status: building` in a response | Queries run against what is indexed so far | Wait for the index; the dashboard's version page shows progress per document |
| Results look stale after a document changed | They should not: the result cache is keyed by the collection's corpus version | Send `"use_cache": false` to confirm; if results are still stale, the document's re-index has not finished |
| `rerank.fallback: true` | The cross-encoder could not load, so the lexical reranker ran | `make logs SERVICE=api` for `cross_encoder_unavailable`; the model is baked into the image, so check the container has enough memory |
| `422 invalid_filter` | The metadata filter uses an unknown operator, a bad field name, or is too deep (more than 32 conditions, depth 4) | `details.path` names the problem; operators are listed in the [LLD](../architecture/LLD.md#metadata-filters) |
| `422 validation_failed` or `invalid_pipeline` when creating a version | A setting outside its rules (`overlap_tokens` above half of `chunk_tokens`, `candidates` below `top_k`), an unknown embedding model, or an unsupported dimension | The message names the field; supported widths are 384, 768, 1024 and 1536 |
| `422 provider_unavailable` when creating a version | The version asks for an `openai` or `ollama` answerer or embedding that this deployment has not configured | Set `LLM_PROVIDER` and `LLM_MODEL` (or the embedding provider) first, or use `extractive` |
| Hits are relevant but ranked low | Fusion or reranking settings suit the content badly | Open the playground, compare two versions side by side, then measure the change with an evaluation run instead of trusting a few queries |

## Answers

| Symptom | Cause | Fix |
| --- | --- | --- |
| The answer says it could not find the answer | The extractive answerer abstains when no passage covers the question | Open the same query in the playground: if the passage is not among the hits, fix retrieval; if it is, raise `max_sources` or `context_tokens` |
| An answer has fewer citations than expected | Markers that point at sources the answerer was not given are removed | Raise `max_sources` so more sources reach the answerer |
| `422 provider_unavailable` on an answer request | The request or the version names a model answerer the deployment has not configured | Set `LLM_PROVIDER` and `LLM_MODEL` ([configuration](configuration.md#model-providers)) |
| `502 upstream_error` ("The model provider could not be reached", "timed out", "returned HTTP 401") | The model provider is down, slow or rejects the key | Check `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`; retrieval and the extractive answerer keep working meanwhile |
| Ollama is unreachable from the containers | `localhost` inside a container is the container | Compose uses `http://host.docker.internal:11434`; make sure Ollama listens on all interfaces (`OLLAMA_HOST=0.0.0.0`) |

## Evaluation

| Symptom | Cause | Fix |
| --- | --- | --- |
| A run stays **queued** | No worker is running | Same as for documents: `make ps`, `make logs SERVICE=worker` |
| Every retrieval metric is 0 | The dataset's `expected_sources.document` values match no document `external_id`, or the evidence sentence is not in the retrieved text | Compare the dataset with the collection's documents; the run page shows each question's expected sources next to what was retrieved |
| Metrics differ between two versions of the same index | Only retrieval settings changed, which is the point | Compare the runs; the configuration diff shows exactly what differed |
| `faithfulness`, `answer_relevance` or `answer_correctness` are missing | The run was started with answers off, the dataset has no reference answers (correctness), or the metric does not apply to the question | Start the run with answers on; add `expected_answer` to the dataset items |
| `422 provider_unavailable` when starting a run with `grader: model` | No judge model is configured | Set `LLM_PROVIDER`, `LLM_MODEL` (and `JUDGE_MODEL` if it differs); otherwise use the deterministic grader |
| `422 empty_dataset` | The dataset has no questions | Import some (`ragkit eval import`) |
| The gate says "no baseline run" | The dataset has no baseline | Mark a good run as the baseline (**Make baseline** on the run page, or `POST .../baseline`) |
| The gate says "not measured" | The metric needs data the run lacks (answers, expected sources) | Run with answers on, or gate on a metric the run measures |
| `409 Only a completed run can be a baseline` | The run is queued, running or failed | Wait for it to complete |
| `ragkit eval gate` exits 2 | The run could not be evaluated (failed, timed out waiting, API unreachable) | Open the run for its error; exit 1 means a real regression |

## The API and the dashboard

| Symptom | Cause | Fix |
| --- | --- | --- |
| The dashboard shows "Cannot reach the RAGKit API" | The API is down or `API_URL` (web) points elsewhere | `curl <api>/livez`; check `API_URL` in the web service's environment, as the browser sees it |
| Every write returns `403 csrf` | The web app's origin is not in `CORS_ORIGINS` (or `WEB_URL`) | Add the exact origin, scheme and port included |
| Signed out after every reload | `COOKIE_SECURE=true` over plain HTTP, or a `COOKIE_DOMAIN` that does not match | Serve over HTTPS, or unset them locally |
| `401 invalid_api_key` | The key is wrong, expired, revoked, or belongs to another project | **Settings, API keys** shows each key's state; create a new one |
| `404` on a project you know exists | You are not a member (a project's existence is not revealed), or the slug is wrong | Ask an owner to add you; check the slug |
| `403 forbidden` ("This needs the editor role in this project.") | A viewer (or a viewer key) tried to change something | Use an editor key or ask for the editor role |
| `429 rate_limited` | Over the per-minute limit | Wait for `Retry-After`; the SDK backs off by itself |
| `503 service_unavailable` on sign-in | Valkey is unreachable, so password guesses cannot be throttled | Fix Valkey; sign-in fails closed on purpose |
| The API refuses to start: "Refusing to start in production" | `APP_ENV=production` with unsafe settings | The message lists every problem; [security.md](../architecture/security.md#production-guard-rails) explains each |
| `/readyz` returns 503 | A dependency is down; the body names it (`database`, `redis`, `storage`, `queue`) | Fix that dependency; the process stays up and recovers on its own |

## On AWS

| Symptom | Cause | Fix |
| --- | --- | --- |
| Worker or API tasks stop with exit code 137 | Out of memory: the embedding model and the reranker need headroom, and too many concurrent jobs add to it | Raise `worker_memory` or `api_memory`, or lower `worker_concurrency` |
| Everyone shares one sign-in limit and gets 429 | The API sees the load balancer's address for every client | `FORWARDED_ALLOW_IPS` must be the VPC range (the module sets it); never `*` |
| `terraform apply` fails on the bucket name | S3 bucket names are global | Use a more specific `name_prefix` |
| The image build fails on an x86 machine | `linux/arm64` images need buildx with QEMU | `docker buildx create --use`, and install QEMU emulation (Docker Desktop includes it) |
| `make aws-cli ... user create` prints no password | A password was given (`--password` or `RAGKIT_USER_PASSWORD`), so none was generated | Use the one you gave, or omit it to get a temporary one in the task log |
| Jobs pile up in the queue | No worker is running, or workers are saturated | The `jobs-backlog` alarm, `aws ecs describe-services`, and [operations.md](operations.md#scaling) |
| A dead-letter alarm fires | A job failed three times | [operations.md](operations.md#dead-letters) |
