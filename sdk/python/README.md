# Euron RAGKit Python SDK

A typed client and command line for [Euron RAGKit](../../README.md): add content, query and
answer with citations, create pipeline versions, run evaluations, compare them, and fail a CI
job when retrieval regresses.

- Python 3.10 or newer; dependencies are `httpx`, `pydantic` and `typer`.
- Every call goes through one transport with the API key, timeouts, and retries that are safe:
  `429` is retried on every call, network and gateway failures only on reads (a retried `POST`
  could start a second evaluation run).
- Responses are typed models that keep fields the SDK does not know yet, so a newer server
  never breaks an older client.

## Install

```bash
pip install ./sdk/python        # from a checkout; the package is euron-ragkit, imported as ragkit
```

## Configure

Arguments win; otherwise the environment is read:

| Variable | Meaning |
| --- | --- |
| `RAGKIT_URL` | API base URL (default `http://localhost:8160`) |
| `RAGKIT_API_KEY` | a project API key, `rgk_...` (**Settings, API keys** in the dashboard) |
| `RAGKIT_PROJECT` | the project slug, for example `acme-payments` |

Use a `viewer` key for an application that only queries, and an `editor` key for scripts that
add content or run evaluations.

## Query and answer

```python
from ragkit import RAGKit

rk = RAGKit()  # RAGKIT_URL, RAGKIT_API_KEY and RAGKIT_PROJECT from the environment
docs = rk.collection("developer-docs")

result = docs.query("How do I verify webhook signatures?", top_k=3, rerank="cross-encoder")
for hit in result.hits:
    print(hit.rank, hit.score, hit.document_title, hit.scores)   # scores: vector, keyword, fused, rerank

answer = docs.answer("What is the request rate limit in live mode?")
print(answer.answer)
for citation in answer.citations:
    print(f"[{citation.n}] {citation.document_title} ({citation.location}): {citation.quote}")
```

Any retrieval setting of a pipeline version can be overridden per call (`mode`, `fusion`,
`rerank`, `candidates`, `filters`, `pipeline_version`, ...), and metadata `filters` narrow the
candidates: `docs.query("payout schedule", filters={"audience": "admins"})`.

## Add content and manage pipelines

```python
docs.add_texts([{"title": "Refund policy", "text": "Refunds take 5 to 10 days.", "external_id": "refunds"}])
docs.add_files(["handbook.pdf", "faq.md"], metadata={"audience": "developers"})
docs.add_urls(["https://example.com/docs/payouts"])
docs.wait_until_indexed()                      # blocks until every document is parsed and indexed

v4 = docs.create_pipeline(
    "Smaller chunks",
    config={"chunking": {"strategy": "recursive", "chunk_tokens": 192, "overlap_tokens": 24}},
)
docs.wait_until_indexed(v4.version)
docs.activate(v4.version)                      # queries use it by default from now on
```

A version that only changes retrieval or answering reuses an existing index and is queryable
at once; `v4.index.shared_with` tells you which.

## Evaluate and gate

```python
rk.evals.create_dataset("Support golden set", "developer-docs", load_jsonl("support-golden.jsonl"), slug="support-golden")

baseline = rk.evals.run("support-golden", pipeline_version=2, label="v2 baseline")
rk.evals.set_baseline(baseline.id)                            # the run later runs are gated against

run = rk.evals.run("support-golden", pipeline_version=4)      # waits for the worker
print(run.means)                                              # hit_rate, mrr, ndcg, faithfulness, ...

comparison = rk.evals.compare([baseline.id, run.id])          # deltas, configuration diff, per-question changes
verdict = rk.evals.gate(run.id, min={"hit_rate": 0.85}, max_drop=0.03)
print(verdict.passed, [check.message for check in verdict.checks])
```

Import `load_jsonl` with `from ragkit import load_jsonl`. Datasets are JSONL, one question per
line with the document (by `external_id`) and the evidence sentence that answers it:

```json
{"question": "What is the request rate limit in live mode?", "expected_sources": [{"document": "rate-limits", "evidence": "Requests per second: 100"}], "expected_answer": "100 requests per second.", "tags": ["lookup"]}
```

## Command line

`pip install` adds a `ragkit` command that reads the same three variables:

```bash
ragkit query developer-docs "How do I verify webhook signatures?" --top-k 3
ragkit answer developer-docs "What is the request rate limit in live mode?"
ragkit ingest developer-docs handbook.pdf faq.md --metadata audience=developers
ragkit eval import support-golden support-golden.jsonl --collection developer-docs
ragkit eval run support-golden --version 4
ragkit eval gate support-golden --version 4 --min hit_rate=0.85 --max-drop 0.03 --report gate.md
```

`ragkit eval gate` starts a run (or takes a finished one with `--run`), waits for it, checks
it against floors and the dataset's baseline, prints a table and exits:

| Exit code | Meaning |
| --- | --- |
| `0` | every check passed |
| `1` | a metric regressed past its threshold |
| `2` | the run could not be evaluated (failed, timed out, API unreachable) |

so a CI job can tell a regression from an outage. `--report` writes the verdict as Markdown
(or JSON with `--format json`) for a pull request comment or a job summary:

```yaml
- run: pip install ./sdk/python
- run: ragkit eval gate support-golden --min hit_rate=0.85 --max-drop 0.03 --report gate.md
  env:
    RAGKIT_URL: ${{ secrets.RAGKIT_URL }}
    RAGKIT_API_KEY: ${{ secrets.RAGKIT_API_KEY }}      # an editor key
    RAGKIT_PROJECT: acme-payments
```

## Errors

Every failure raises a `RAGKitError` that carries the server's error envelope
(`status`, `code`, `message`, `request_id`, `details`). Subclasses: `AuthenticationError`
(401), `PermissionDeniedError` (403), `NotFoundError` (404), `ValidationError` (422, with
`details` pointing at the field) and `RateLimitError` (429, raised after the retries run out).
Quote the `request_id` when you report a problem.

## Develop

```bash
cd sdk/python
uv sync
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

The server's integration suite also drives this SDK against a live API
(`apps/api/tests/integration/test_sdk.py`).
