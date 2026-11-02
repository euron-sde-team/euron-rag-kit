# Testing

RAGKit has seven suites, from milliseconds to minutes. Each one owns a layer, and the browser
suites run against the real stack seeded by `make demo`.

| Suite | Command | Count | Runs against |
| --- | --- | --- | --- |
| API unit | `make test` (with the SDK and web unit tests) | 166 | Nothing external: pure modules (chunkers, fusion, metrics, filters, parsers, security) and fakes for the ports |
| SDK | `make test` | 14 | The SDK against a mocked HTTP transport, and the CLI through Typer's test runner |
| Web unit | `make test` | 47 | The dashboard's pure logic (`apps/web/src/lib`), in Node |
| API integration | `make test-integration` | 59 | Real PostgreSQL 16 with pgvector, Valkey 8 and Floci (S3, SQS, KMS), the bundled embedding model and reranker, and the SDK driving a live server |
| End to end | `make e2e` | 27 | The running stack in Chromium |
| QA crawl | `make qa` | 4 | Every page at desktop and mobile widths, with axe |
| Screenshots | `make screenshots` | 3 | The README images and the tour GIF, from the seeded data |

## API unit tests

```bash
make test                                                     # API unit + SDK + web unit
uv --directory apps/api run pytest tests/unit -q              # API unit only
uv --directory apps/api run pytest tests/unit/test_metrics.py -q
```

`apps/api/tests/unit` covers the modules that hold the product's rules, each with worked
examples you can check by hand:

| Area | Files |
| --- | --- |
| Pipeline configuration: validation, defaults, the index fingerprint and what does and does not change it | `test_pipeline_config.py` |
| Parsing and sniffing: the six formats, extension against magic bytes, archive guards, text intake | `test_parsers.py`, `test_sniff.py`, `test_intake.py`, `test_text.py` |
| Cleaning rules and the removal report | `test_cleaning.py` |
| The three chunkers: windows, structure, sentence windows, overlap, headings that never end a chunk | `test_chunkers.py`, `test_tokens.py` |
| Embeddings: the registry, normalisation, the deterministic hash embedder, caching | `test_embeddings.py` |
| Retrieval math: RRF and weighted fusion, the metadata filter compiler (injection attempts included), the lexical and cross-encoder rerankers, context packing | `test_fusion.py`, `test_filters.py`, `test_rerankers.py` |
| Answers: the extractive answerer (numbers, tables, abstaining), model answerers against mocked HTTP, citation verification, the model judge | `test_extractive.py`, `test_answerers.py`, `test_judge.py` |
| Evaluation: relevance by evidence, every metric on hand-computed cases, aggregation, run comparison, the regression gate | `test_metrics.py`, `test_gate_and_compare.py` |
| The URL fetcher's SSRF guards, redirects and the job queue messages | `test_fetcher_and_queue.py` |
| Passwords, sessions, API keys and the rate limiter | `test_security.py` |
| The error envelope, request ids, body limits | `test_http_layer.py` |
| Configuration and the production guard rails | `test_config.py` |
| The operator CLI's account creation | `test_cli.py` |

## API integration tests

```bash
make test-integration       # starts the dependencies if needed, then runs the suite
```

`scripts/test-deps.sh` starts PostgreSQL (pgvector), Valkey and Floci from the compose files
(it reuses them if the stack is already running). The suite creates a database of its own
(`ragkit_test`, recreated every run), uses Valkey database 15 and makes uniquely named
buckets, keys and queues on the emulator, so the development data is never touched. Point it
at other services with `TEST_DATABASE_ADMIN_URL`, `TEST_REDIS_URL` and
`TEST_AWS_ENDPOINT_URL`.

The suite migrates a fresh schema, uploads the sample corpus through the API (`httpx` against
the ASGI app) and drives everything the way a client does:

| Area | File |
| --- | --- |
| Project isolation: an outsider gets 404 from every project route (swept from the OpenAPI document), ids from another project resolve to nothing, roles, API keys and revocation, the cookie origin check, uniform sign-in errors | `test_access.py` |
| Ingestion: every format parsed and indexed, originals in S3 with KMS, duplicates and bad files reported per file, text and URL sources, metadata changes reaching chunks without a rebuild, deletion, reprocessing | `test_ingestion.py` |
| Pipeline versions: retrieval-only changes share an index, index changes build one in the background, activation, refused configurations, previews that persist nothing | `test_pipelines.py` |
| Retrieval: every stage reported, each mode running only its stages, weighted fusion, filters on both searches, document scoping, caching until the corpus changes, cited answers, an OpenAI-compatible model through the same endpoint, the bundled models, analytics | `test_retrieval.py` |
| Evaluation: datasets refusing unknown documents, a run measuring every question, comparisons and the gate against a baseline, shared indexes, JSONL export and import, deleting runs | `test_evaluation.py` |
| The worker over SQS: parse and index jobs, an unreadable file failing once, evaluation runs, malformed messages, the reaper (lost messages, backlogs, exhausted attempts), duplicate deliveries, handing jobs back on shutdown | `test_worker.py` |
| Platform: probes, metrics and capabilities, request ids, the OpenAPI document, idempotent migrations, S3 round trips, rate limits counted in Valkey, serving without Valkey | `test_platform.py` |
| The Python SDK and its CLI against a live server: ingest, query, answer, evaluate, gate | `test_sdk.py` |

## Web and SDK unit tests

```bash
pnpm --filter @ragkit/web test
uv --directory sdk/python run pytest -q
```

Vitest covers the dashboard's helpers: the API client (errors, downloads), metric and run
formatting, pipeline drafts and their index-reuse rules, JSONL parsing, citation and highlight
logic, snippets, activity phrasing and the runtime configuration. The SDK tests use `respx` to
check request shapes, retries with back-off (safe methods and idempotent failures only), error
mapping and the gate's exit codes.

## Browser suites

The three Playwright projects in `e2e/` run against a stack started with
`make up && make demo`, in Chromium at 1440x900. They sign in once per demo person and reuse
the session cookie (the API allows ten sign-ins a minute per address).

```bash
make e2e            # user journeys
make qa             # the crawl
make screenshots    # README images and docs/assets/tour.gif
```

The suites share the demo database, so run them in this order on a fresh stack: the QA crawl
and the screenshots only read, while the end-to-end suite adds a pipeline version, an
evaluation run and an API key (and changes a password and back).

**End to end** (`e2e/tests`): signing in, a wrong password, the redirect back to where you
were going, a viewer who sees no editing controls, the theme toggle, changing a password and
signing in with the new one; the collections list, the documents table with its filter, a
document's parsed sections and indexes, and adding and deleting a text source that becomes
ready in every index; the pipeline versions list, a version's configuration, size histogram and
chunk context windows, the new-version form telling you whether a change reuses an index or
builds one (and creating a reranker-only version), and refusing an invalid draft; the
playground with every stage's score, a cited answer whose citation opens its quote, two
versions side by side, and overrides with metadata filters; the evaluation runs table, a
comparison metric by metric and setting by setting, a run's gate verdict and per-question
evidence, starting a run that the worker really scores, and a dataset with its gate
thresholds; analytics with a top query that opens in the playground; members, an API key that
is shown once, works against the API and stops working once revoked, and the activity trail.

**QA crawl** (`e2e/qa`): every page and tab, signed out and signed in, at 1440x900 and at
390x844. A page fails on a console error, an uncaught exception, a failed or 4xx/5xx request,
sideways scrolling (of the page or its scroll container), a broken internal link, or a
serious or critical axe violation (WCAG 2 A and AA). A full capture of every page lands in
`e2e/.qa/` for a visual review.

**Screenshots** (`e2e/capture`): seventeen pages at 1440x900 and 2x device pixel ratio in
`docs/assets/screenshots/`, and the tour frames assembled into `docs/assets/tour.gif` by
`e2e/capture/make-gif.mjs` (pure JavaScript, no ffmpeg).

## Static checks

```bash
make lint        # ruff check + format check, ESLint, Prettier
make typecheck   # mypy (strict) for the server and the SDK, and tsc
make sanitize    # credentials, cloud identifiers and typographic dashes in committable files
make tf-fmt tf-validate tf-lint tf-security
```

`.github/workflows/checks.yml` runs the fast checks on every push and pull request; the full
pipeline (integration tests, images, the browser suites, security scans) is in
`.github/workflows-full/`, ready to enable.
