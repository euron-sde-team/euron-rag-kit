"""Evaluation end to end: datasets, runs, metrics, comparisons, baselines and the gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from ragkit_server.evaluation.metrics import METRICS
from tests.integration.conftest import Corpus
from tests.integration.support import HASH_PIPELINE, wait_run

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def smoke_items(samples_dir: Path) -> list[dict[str, Any]]:
    lines = (samples_dir / "datasets" / "smoke.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture(scope="module")
async def smoke(
    client: httpx.AsyncClient, corpus: Corpus, smoke_items: list[dict[str, Any]]
) -> str:
    response = await client.post(
        f"/api/v1/projects/{corpus.project}/datasets",
        json={
            "name": "Smoke",
            "slug": "smoke",
            "collection": corpus.collection,
            "gate": {"min": {"hit_rate": 0.5}, "max_drop": 0.2},
            "items": smoke_items,
        },
        headers=corpus.owner.headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["item_count"] == len(smoke_items)
    return "smoke"


async def start(client: httpx.AsyncClient, corpus: Corpus, **body: Any) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{corpus.project}/eval-runs", json=body, headers=corpus.owner.headers
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return await wait_run(client, corpus.owner, corpus.project, created["id"])


async def test_datasets_refuse_unknown_documents(client: httpx.AsyncClient, corpus: Corpus) -> None:
    response = await client.post(
        f"/api/v1/projects/{corpus.project}/datasets",
        json={
            "name": "Typos",
            "collection": corpus.collection,
            "items": [{"question": "q?", "expected_sources": [{"document": "webhook"}]}],
        },
        headers=corpus.owner.headers,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_documents"
    assert response.json()["error"]["details"] == {"unknown": ["webhook"]}


async def test_a_run_measures_every_question(
    client: httpx.AsyncClient, corpus: Corpus, smoke: str
) -> None:
    run = await start(client, corpus, dataset=smoke, k=5)
    assert run["status"] == "completed", run["error"]
    assert run["completed_items"] == run["total_items"] == 8
    assert run["label"] == "v1 recursive, hybrid + lexical"
    assert run["config"]["retrieval"]["top_k"] == 5
    assert run["config"]["evaluation"] == {"k": 5, "grader": "deterministic", "answers": True}
    means = run["metrics"]["means"]
    assert set(means) == set(METRICS)
    assert all(0.0 <= value <= 1.0 for value in means.values())
    assert means["hit_rate"] >= 0.75
    assert run["metrics"]["counts"]["answer_correctness"] == 8
    assert "keyword" in run["metrics"]["by_tag"]
    assert run["metrics"]["latency_ms"]["p95"] >= run["metrics"]["latency_ms"]["p50"]

    results = (
        await client.get(
            f"/api/v1/projects/{corpus.project}/eval-runs/{run['id']}/results",
            headers=corpus.owner.headers,
        )
    ).json()
    assert results["total"] == 8
    first = results["items"][0]
    assert first["expected_sources"]
    assert first["answer"]
    assert len(first["retrieved"]) == 5
    assert {"rank", "external_id", "relevant", "covers", "score"} <= set(first["retrieved"][0])
    hits = [r for r in results["items"] if r["metrics"]["hit_rate"] == 1.0]
    assert all(any(c["relevant"] for c in r["retrieved"]) for r in hits)


async def test_runs_compare_side_by_side_and_gate_on_a_baseline(
    client: httpx.AsyncClient, corpus: Corpus, smoke: str
) -> None:
    project = f"/api/v1/projects/{corpus.project}"
    baseline = await start(client, corpus, dataset=smoke, label="baseline")
    keyword = await start(
        client, corpus, dataset=smoke, retrieval={"mode": "keyword", "rerank": "none"}
    )
    assert keyword["label"] == "v1 recursive, keyword"
    assert keyword["config"]["retrieval"]["mode"] == "keyword"

    comparison = (
        await client.get(
            f"{project}/eval-runs/compare",
            params={"ids": f"{baseline['id']},{keyword['id']}"},
            headers=corpus.owner.headers,
        )
    ).json()
    assert comparison["same_dataset"] is True
    assert [run["id"] for run in comparison["runs"]] == [baseline["id"], keyword["id"]]
    assert {"key": "retrieval.mode", "values": ["hybrid", "keyword"]} in comparison["config_diff"]
    mrr = next(row for row in comparison["metrics"] if row["metric"] == "mrr")
    assert mrr["deltas"][0] == 0.0
    assert mrr["values"][1] - mrr["values"][0] == pytest.approx(mrr["deltas"][1], abs=1e-3)
    assert len(comparison["questions"]) == 8
    assert sum(comparison["summary"].values()) == 8

    marked = await client.post(
        f"{project}/eval-runs/{baseline['id']}/baseline", headers=corpus.owner.headers
    )
    assert marked.json()["is_baseline"] is True
    dataset = (await client.get(f"{project}/datasets/{smoke}", headers=corpus.owner.headers)).json()
    assert dataset["baseline_run_id"] == baseline["id"]

    gate = (
        await client.post(
            f"{project}/eval-runs/{baseline['id']}/gate", json={}, headers=corpus.owner.headers
        )
    ).json()
    assert gate["passed"] is True
    assert gate["baseline_run_id"] == baseline["id"]
    assert {check["kind"] for check in gate["checks"]} == {"min", "max_drop"}

    strict = (
        await client.post(
            f"{project}/eval-runs/{keyword['id']}/gate",
            json={"min": {"hit_rate": 1.01}, "max_drop": 0.0},
            headers=corpus.owner.headers,
        )
    ).json()
    assert strict["passed"] is False
    failing = {(c["metric"], c["kind"]) for c in strict["checks"] if not c["passed"]}
    assert ("hit_rate", "min") in failing

    unknown = await client.post(
        f"{project}/eval-runs/{baseline['id']}/gate",
        json={"min": {"accuracy": 0.9}},
        headers=corpus.owner.headers,
    )
    assert unknown.status_code == 422


async def test_runs_against_a_shared_index_version(
    client: httpx.AsyncClient, corpus: Corpus, smoke: str
) -> None:
    created = await client.post(
        f"{corpus.base}/pipelines",
        json={
            "name": "Vector only",
            "config": {**HASH_PIPELINE, "retrieval": {"mode": "vector", "rerank": "none"}},
        },
        headers=corpus.owner.headers,
    )
    version = created.json()["version"]
    run = await start(client, corpus, dataset=smoke, pipeline_version=version, answers=False)
    assert run["status"] == "completed"
    assert run["pipeline_version"] == version
    assert "faithfulness" not in run["metrics"]["means"]
    assert "hit_rate" in run["metrics"]["means"]


async def test_datasets_export_and_import_as_jsonl(
    client: httpx.AsyncClient, corpus: Corpus, smoke: str
) -> None:
    project = f"/api/v1/projects/{corpus.project}"
    exported = await client.get(f"{project}/datasets/{smoke}/export", headers=corpus.owner.headers)
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    items = [json.loads(line) for line in exported.text.splitlines()]
    assert len(items) == 8
    copy = await client.post(
        f"{project}/datasets",
        json={"name": "Copy", "collection": corpus.collection, "items": items[:3]},
        headers=corpus.owner.headers,
    )
    assert copy.status_code == 201
    replaced = await client.post(
        f"{project}/datasets/copy/items",
        json={"items": items[3:5], "replace": True},
        headers=corpus.owner.headers,
    )
    assert replaced.json()["item_count"] == 2
    listed = (
        await client.get(f"{project}/datasets/copy/items", headers=corpus.owner.headers)
    ).json()
    removed = await client.delete(
        f"{project}/datasets/copy/items/{listed['items'][0]['id']}", headers=corpus.owner.headers
    )
    assert removed.status_code == 204
    datasets = {
        d["slug"]: d
        for d in (await client.get(f"{project}/datasets", headers=corpus.owner.headers)).json()
    }
    assert datasets["copy"]["item_count"] == 1
    assert datasets[smoke]["last_run"] is not None


async def test_runs_need_questions_and_a_configured_grader(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    project = f"/api/v1/projects/{corpus.project}"
    await client.post(
        f"{project}/datasets",
        json={"name": "Empty", "collection": corpus.collection},
        headers=corpus.owner.headers,
    )
    empty = await client.post(
        f"{project}/eval-runs", json={"dataset": "empty"}, headers=corpus.owner.headers
    )
    assert empty.json()["error"]["code"] == "empty_dataset"
    model = await client.post(
        f"{project}/eval-runs",
        json={"dataset": "smoke", "grader": "model"},
        headers=corpus.owner.headers,
    )
    assert model.status_code == 422
    assert model.json()["error"]["code"] == "provider_unavailable"


async def test_finished_runs_can_be_deleted(
    client: httpx.AsyncClient, corpus: Corpus, smoke: str
) -> None:
    run = await start(client, corpus, dataset=smoke, answers=False, label="to delete")
    project = f"/api/v1/projects/{corpus.project}"
    assert (
        await client.delete(f"{project}/eval-runs/{run['id']}", headers=corpus.owner.headers)
    ).status_code == 204
    assert (
        await client.get(f"{project}/eval-runs/{run['id']}", headers=corpus.owner.headers)
    ).status_code == 404
    listing = (
        await client.get(
            f"{project}/eval-runs",
            params={"dataset": smoke, "status": "completed"},
            headers=corpus.owner.headers,
        )
    ).json()
    assert all(item["dataset"]["slug"] == smoke for item in listing["items"])
