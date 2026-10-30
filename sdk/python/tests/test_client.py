from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from ragkit import RAGKit, load_jsonl
from ragkit.errors import AuthenticationError, RAGKitError, RateLimitError, ValidationError
from tests.conftest import PROJECT, hit_body, run_body

DOCS = f"{PROJECT}/collections/developer-docs"


def test_configuration_comes_from_arguments_or_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert RAGKit().project == "acme-payments"
    monkeypatch.delenv("RAGKIT_API_KEY")
    with pytest.raises(RAGKitError, match="RAGKIT_API_KEY"):
        RAGKit()
    assert RAGKit(api_key="rgk_x", project="other").project == "other"


def test_query_sends_options_and_parses_stage_scores(api: respx.MockRouter) -> None:
    route = api.post(f"{DOCS}/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "verify webhooks",
                "pipeline_version": 2,
                "index_id": "idx",
                "index_status": "ready",
                "mode": "hybrid",
                "fusion": "rrf",
                "rerank": {"kind": "cross-encoder", "fallback": False},
                "hits": [hit_body(1), hit_body(2)],
                "candidates": {"vector": 40, "keyword": 12, "fused": 40},
                "timings_ms": {"total": 41.5},
                "cached": False,
            },
        )
    )
    with RAGKit() as rk:
        result = rk.collection("developer-docs").query(
            "verify webhooks", top_k=2, filters={"section": "guides"}
        )
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"query": "verify webhooks", "top_k": 2, "filters": {"section": "guides"}}
    assert route.calls.last.request.headers["authorization"] == "Bearer rgk_testprefix_secret"
    assert [h.rank for h in result.hits] == [1, 2]
    assert result.hits[0].scores["rerank"] == 0.91
    assert result.hits[0].passage.startswith("Compute an HMAC")


def test_errors_carry_the_envelope(api: respx.MockRouter) -> None:
    api.post(f"{DOCS}/query").mock(
        return_value=httpx.Response(
            422,
            json={
                "error": {
                    "code": "invalid_filter",
                    "message": "filters.x: bad",
                    "request_id": "req-9",
                }
            },
        )
    )
    api.get(f"{PROJECT}/collections").mock(
        return_value=httpx.Response(
            401, json={"error": {"code": "invalid_api_key", "message": "nope"}}
        )
    )
    with RAGKit() as rk:
        with pytest.raises(ValidationError) as invalid:
            rk.collection("developer-docs").query("x", filters={"x": {"$regex": "y"}})
        with pytest.raises(AuthenticationError):
            rk.collections()
    assert invalid.value.code == "invalid_filter"
    assert invalid.value.request_id == "req-9"
    assert "req-9" in str(invalid.value)


def test_rate_limits_are_retried_then_raised(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ragkit._http.time.sleep", lambda _: None)
    route = api.get(f"{PROJECT}/collections").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"retry-after": "1"},
                json={"error": {"code": "rate_limited", "message": "slow"}},
            ),
            httpx.Response(200, json=[]),
        ]
    )
    with RAGKit() as rk:
        assert rk.collections() == []
    assert route.call_count == 2
    api.get(f"{PROJECT}/datasets").mock(
        return_value=httpx.Response(
            429, json={"error": {"code": "rate_limited", "message": "slow"}}
        )
    )
    with RAGKit(max_retries=1) as rk, pytest.raises(RateLimitError):
        rk.evals.datasets()


def test_gateway_errors_retry_reads_but_never_writes(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ragkit._http.time.sleep", lambda _: None)
    reads = api.get(f"{PROJECT}/eval-runs/run-1").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=run_body())]
    )
    writes = api.post(f"{PROJECT}/eval-runs").mock(return_value=httpx.Response(503))
    with RAGKit() as rk:
        assert rk.evals.get("run-1").status == "completed"
        with pytest.raises(RAGKitError):
            rk.evals.run("smoke", wait=False)
    assert reads.call_count == 2
    assert writes.call_count == 1


def test_documents_are_paged_through(api: respx.MockRouter) -> None:
    def page(offset: int, count: int) -> httpx.Response:
        items = [
            {
                "id": f"d{offset + i}",
                "external_id": f"doc-{offset + i}",
                "title": "Doc",
                "source_type": "text",
                "status": "ready",
                "created_at": "2026-10-30T10:00:00Z",
            }
            for i in range(count)
        ]
        return httpx.Response(200, json={"items": items, "total": 3, "limit": 2, "offset": offset})

    api.get(f"{DOCS}/documents", params={"offset": "0"}).mock(return_value=page(0, 2))
    api.get(f"{DOCS}/documents", params={"offset": "2"}).mock(return_value=page(2, 1))
    with RAGKit() as rk:
        ids = [d.external_id for d in rk.collection("developer-docs").documents(page_size=2)]
    assert ids == ["doc-0", "doc-1", "doc-2"]


def test_texts_are_imported_in_batches(api: respx.MockRouter) -> None:
    route = api.post(f"{DOCS}/documents/import").mock(
        return_value=httpx.Response(201, json={"created": [], "duplicates": [], "rejected": []})
    )
    items = [{"title": f"Note {i}", "text": "body"} for i in range(150)]
    with RAGKit() as rk:
        rk.collection("developer-docs").add_texts(items)
    batches = [json.loads(call.request.content)["items"] for call in route.calls]
    assert [len(b) for b in batches] == [100, 50]
    assert batches[0][0]["type"] == "text"


def test_runs_wait_until_finished(api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ragkit.client.time.sleep", lambda _: None)
    api.post(f"{PROJECT}/eval-runs").mock(
        return_value=httpx.Response(201, json=run_body(status="queued"))
    )
    api.get(f"{PROJECT}/eval-runs/run-1").mock(
        side_effect=[
            httpx.Response(200, json=run_body(status="running", completed_items=3)),
            httpx.Response(200, json=run_body()),
        ]
    )
    with RAGKit() as rk:
        run = rk.evals.run("smoke", pipeline_version=2)
    assert run.finished
    assert run.means["hit_rate"] == 0.95


def test_jsonl_loading_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "items.jsonl"
    path.write_text('{"question": "a?"}\n\n{"question": "b?"}\n')
    assert [item["question"] for item in load_jsonl(path)] == ["a?", "b?"]
