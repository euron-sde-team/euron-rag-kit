"""Prometheus metrics, exposed at GET /metrics (and by the worker on WORKER_METRICS_PORT).

One API process per container (scale out with containers, not uvicorn workers), so the
default registry is accurate without multiprocess mode.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "ragkit_http_requests_total", "HTTP requests by route template.", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "ragkit_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
DOCUMENTS_PARSED = Counter(
    "ragkit_documents_parsed_total", "Documents parsed by the worker.", ["kind", "outcome"]
)
INDEX_ENTRIES = Counter(
    "ragkit_index_entries_total", "Documents chunked and embedded into an index.", ["outcome"]
)
INDEX_DURATION = Histogram(
    "ragkit_index_entry_duration_seconds",
    "Clean, chunk and embed time per document per index.",
    ["strategy"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
CHUNKS_WRITTEN = Counter("ragkit_chunks_written_total", "Chunks written to indexes.", ["strategy"])
RETRIEVAL_STAGE = Histogram(
    "ragkit_retrieval_stage_seconds",
    "Retrieval latency by stage: embed, vector, keyword, fusion, rerank, total.",
    ["stage"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
QUERIES = Counter("ragkit_queries_total", "Retrieval requests by kind and mode.", ["kind", "mode"])
ANSWER_DURATION = Histogram(
    "ragkit_answer_duration_seconds",
    "Answer generation latency by answerer.",
    ["answerer"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
EVAL_RUNS = Counter("ragkit_eval_runs_total", "Evaluation runs by outcome.", ["outcome"])
CACHE = Counter("ragkit_cache_total", "Cache lookups by cache and result.", ["cache", "result"])
RERANK_FALLBACKS = Counter(
    "ragkit_rerank_fallbacks_total", "Cross-encoder reranks served by the lexical fallback."
)
