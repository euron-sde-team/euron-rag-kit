"""The RAGKit client.

from ragkit import RAGKit

rk = RAGKit()  # RAGKIT_URL, RAGKIT_API_KEY and RAGKIT_PROJECT from the environment
docs = rk.collection("developer-docs")
docs.add_texts([{"title": "Refund policy", "text": "Refunds take 5 to 10 days."}])
docs.wait_until_indexed()
result = docs.query("How long do refunds take?", top_k=3)
run = rk.evals.run("support-golden", pipeline_version=2)
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from ragkit._http import Transport
from ragkit.errors import RAGKitError
from ragkit.errors import TimeoutError as WaitTimeout
from ragkit.models import (
    Answer,
    Collection,
    Comparison,
    Dataset,
    Document,
    GateResult,
    IngestResult,
    PipelineVersion,
    QueryResult,
    Run,
    RunResult,
)

FILES_PER_REQUEST = 20
TEXTS_PER_REQUEST = 100


def _segment(value: str) -> str:
    return quote(value, safe="")


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Dataset items, one JSON object per line (blank lines are skipped)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class RAGKit:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        project: str | None = None,
        *,
        timeout: float = 60.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = base_url or os.environ.get("RAGKIT_URL") or "http://localhost:8160"
        key = api_key or os.environ.get("RAGKIT_API_KEY")
        self.project = project or os.environ.get("RAGKIT_PROJECT") or ""
        if not key:
            raise RAGKitError("Set api_key or RAGKIT_API_KEY.", code="configuration")
        if not self.project:
            raise RAGKitError("Set project or RAGKIT_PROJECT.", code="configuration")
        self.http = Transport(
            url, key, timeout=timeout, max_retries=max_retries, transport=transport
        )
        self.evals = Evals(self)

    @property
    def base(self) -> str:
        return f"/api/v1/projects/{_segment(self.project)}"

    def collections(self) -> list[Collection]:
        return [
            Collection.model_validate(c)
            for c in self.http.request("GET", f"{self.base}/collections")
        ]

    def collection(self, slug: str) -> CollectionClient:
        return CollectionClient(self, slug)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> RAGKit:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class CollectionClient:
    """One collection: ingest sources, follow indexing, query and answer."""

    def __init__(self, client: RAGKit, slug: str) -> None:
        self._client = client
        self.slug = slug

    @property
    def _http(self) -> Transport:
        return self._client.http

    @property
    def path(self) -> str:
        return f"{self._client.base}/collections/{_segment(self.slug)}"

    def info(self) -> Collection:
        return Collection.model_validate(self._http.request("GET", self.path))

    # Ingestion ----------------------------------------------------------------------------

    def add_texts(self, items: Iterable[Mapping[str, Any]]) -> IngestResult:
        """Text sources: {"title", "text", "format"?, "external_id"?, "metadata"?}."""
        sources = [{"type": "text", **item} for item in items]
        return self._import(sources)

    def add_urls(
        self, urls: Iterable[str], *, metadata: Mapping[str, Any] | None = None
    ) -> IngestResult:
        sources = [{"type": "url", "url": url, "metadata": dict(metadata or {})} for url in urls]
        return self._import(sources)

    def _import(self, sources: list[dict[str, Any]]) -> IngestResult:
        merged = IngestResult(created=[], duplicates=[], rejected=[])
        for start in range(0, len(sources), TEXTS_PER_REQUEST):
            batch = sources[start : start + TEXTS_PER_REQUEST]
            result = IngestResult.model_validate(
                self._http.request("POST", f"{self.path}/documents/import", json={"items": batch})
            )
            merged.created += result.created
            merged.duplicates += result.duplicates
            merged.rejected += result.rejected
        return merged

    def add_files(
        self, paths: Iterable[str | Path], *, metadata: Mapping[str, Any] | None = None
    ) -> IngestResult:
        files = [Path(p) for p in paths]
        merged = IngestResult(created=[], duplicates=[], rejected=[])
        for start in range(0, len(files), FILES_PER_REQUEST):
            batch = files[start : start + FILES_PER_REQUEST]
            parts = [
                (
                    "files",
                    (
                        path.name,
                        path.read_bytes(),
                        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    ),
                )
                for path in batch
            ]
            result = IngestResult.model_validate(
                self._http.request(
                    "POST",
                    f"{self.path}/documents",
                    files=parts,
                    data={"metadata": json.dumps(dict(metadata or {}))},
                )
            )
            merged.created += result.created
            merged.duplicates += result.duplicates
            merged.rejected += result.rejected
        return merged

    def documents(
        self, *, status: str | None = None, query: str | None = None, page_size: int = 100
    ) -> Iterator[Document]:
        """Every document, page by page."""
        offset = 0
        while True:
            page = self._http.request(
                "GET",
                f"{self.path}/documents",
                params={"status": status, "q": query, "limit": page_size, "offset": offset},
            )
            for item in page["items"]:
                yield Document.model_validate(item)
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                return

    # Pipelines ----------------------------------------------------------------------------

    def pipelines(self) -> list[PipelineVersion]:
        return [
            PipelineVersion.model_validate(v)
            for v in self._http.request("GET", f"{self.path}/pipelines")
        ]

    def pipeline(self, version: int | None = None) -> PipelineVersion:
        """A version, or the active one."""
        if version is None:
            active = self.info().active_version
            if active is None:
                raise RAGKitError("The collection has no active pipeline version.")
            version = active
        return PipelineVersion.model_validate(
            self._http.request("GET", f"{self.path}/pipelines/{version}")
        )

    def create_pipeline(
        self,
        name: str,
        config: Mapping[str, Any],
        *,
        description: str = "",
        activate: bool = False,
    ) -> PipelineVersion:
        body = {
            "name": name,
            "description": description,
            "config": dict(config),
            "activate": activate,
        }
        return PipelineVersion.model_validate(
            self._http.request("POST", f"{self.path}/pipelines", json=body)
        )

    def activate(self, version: int) -> PipelineVersion:
        return PipelineVersion.model_validate(
            self._http.request("POST", f"{self.path}/pipelines/{version}/activate")
        )

    def wait_until_indexed(
        self, version: int | None = None, *, timeout: float = 600.0, poll: float = 2.0
    ) -> PipelineVersion:
        """Block until every document is parsed and the version's index is built."""
        deadline = time.monotonic() + timeout
        while True:
            pending = any(True for _ in self.documents(status="queued")) or any(
                True for _ in self.documents(status="processing")
            )
            current = self.pipeline(version)
            if not pending and current.index.status in ("ready", "empty", "failed"):
                return current
            if time.monotonic() > deadline:
                raise WaitTimeout(
                    f"Version {current.version} is still {current.index.status}.",
                    code="timeout",
                )
            time.sleep(poll)

    # Serving ------------------------------------------------------------------------------

    def query(self, query: str, **options: Any) -> QueryResult:
        """Retrieve passages. Options: top_k, mode, fusion, rerank, filters, pipeline_version
        and the other retrieval settings of a pipeline version."""
        return QueryResult.model_validate(
            self._http.request("POST", f"{self.path}/query", json={"query": query, **options})
        )

    def answer(self, query: str, **options: Any) -> Answer:
        """Retrieve, then answer with citations. Options as for query, plus answerer, model,
        max_sources and context_tokens."""
        return Answer.model_validate(
            self._http.request("POST", f"{self.path}/answer", json={"query": query, **options})
        )


class Evals:
    """Datasets, evaluation runs, comparisons and the regression gate."""

    def __init__(self, client: RAGKit) -> None:
        self._client = client

    @property
    def _http(self) -> Transport:
        return self._client.http

    @property
    def _datasets(self) -> str:
        return f"{self._client.base}/datasets"

    @property
    def _runs(self) -> str:
        return f"{self._client.base}/eval-runs"

    def datasets(self) -> list[Dataset]:
        return [Dataset.model_validate(d) for d in self._http.request("GET", self._datasets)]

    def dataset(self, slug: str) -> Dataset:
        return Dataset.model_validate(
            self._http.request("GET", f"{self._datasets}/{_segment(slug)}")
        )

    def create_dataset(
        self,
        name: str,
        collection: str,
        items: Iterable[Mapping[str, Any]] = (),
        *,
        slug: str | None = None,
        description: str = "",
        gate: Mapping[str, Any] | None = None,
    ) -> Dataset:
        body: dict[str, Any] = {
            "name": name,
            "collection": collection,
            "description": description,
            "items": [dict(item) for item in items],
        }
        if slug:
            body["slug"] = slug
        if gate is not None:
            body["gate"] = dict(gate)
        return Dataset.model_validate(self._http.request("POST", self._datasets, json=body))

    def import_items(
        self, dataset: str, items: Iterable[Mapping[str, Any]], *, replace: bool = False
    ) -> Dataset:
        body = {"items": [dict(item) for item in items], "replace": replace}
        return Dataset.model_validate(
            self._http.request("POST", f"{self._datasets}/{_segment(dataset)}/items", json=body)
        )

    def run(
        self,
        dataset: str,
        *,
        pipeline_version: int | None = None,
        k: int = 5,
        label: str | None = None,
        grader: str = "deterministic",
        answers: bool = True,
        retrieval: Mapping[str, Any] | None = None,
        wait: bool = True,
        timeout: float = 1800.0,
    ) -> Run:
        """Start a run of a dataset against a version (the active one by default)."""
        body: dict[str, Any] = {"dataset": dataset, "k": k, "grader": grader, "answers": answers}
        if pipeline_version is not None:
            body["pipeline_version"] = pipeline_version
        if label:
            body["label"] = label
        if retrieval:
            body["retrieval"] = dict(retrieval)
        run = Run.model_validate(self._http.request("POST", self._runs, json=body))
        return self.wait(run.id, timeout=timeout) if wait else run

    def get(self, run_id: str) -> Run:
        return Run.model_validate(self._http.request("GET", f"{self._runs}/{run_id}"))

    def wait(self, run_id: str, *, timeout: float = 1800.0, poll: float = 3.0) -> Run:
        deadline = time.monotonic() + timeout
        while True:
            run = self.get(run_id)
            if run.finished:
                return run
            if time.monotonic() > deadline:
                raise WaitTimeout(
                    f"Run {run_id} is still {run.status} ({run.completed_items}/"
                    f"{run.total_items}).",
                    code="timeout",
                )
            time.sleep(poll)

    def results(self, run_id: str, *, page_size: int = 200) -> list[RunResult]:
        results: list[RunResult] = []
        while True:
            page = self._http.request(
                "GET",
                f"{self._runs}/{run_id}/results",
                params={"limit": page_size, "offset": len(results)},
            )
            results += [RunResult.model_validate(r) for r in page["items"]]
            if not page["items"] or len(results) >= page["total"]:
                return results

    def compare(self, run_ids: Iterable[str]) -> Comparison:
        ids = ",".join(run_ids)
        return Comparison.model_validate(
            self._http.request("GET", f"{self._runs}/compare", params={"ids": ids})
        )

    def gate(
        self,
        run_id: str,
        *,
        min: Mapping[str, float] | None = None,
        max_drop: float | Mapping[str, float] | None = None,
        baseline_run_id: str | None = None,
    ) -> GateResult:
        """Check a finished run against floors and its dataset's baseline run.

        Thresholds left out come from the dataset's stored gate settings.
        """
        body: dict[str, Any] = {}
        if min is not None:
            body["min"] = dict(min)
        if max_drop is not None:
            body["max_drop"] = max_drop if isinstance(max_drop, float | int) else dict(max_drop)
        if baseline_run_id:
            body["baseline_run_id"] = baseline_run_id
        return GateResult.model_validate(
            self._http.request("POST", f"{self._runs}/{run_id}/gate", json=body)
        )

    def set_baseline(self, run_id: str) -> Run:
        return Run.model_validate(self._http.request("POST", f"{self._runs}/{run_id}/baseline"))
