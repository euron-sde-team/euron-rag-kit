"""Serving: retrieval modes with stage scores, filters, reranking, caching, cited answers,
model answerers, the bundled local models and query analytics."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from ragkit_server.core.config import Settings
from ragkit_server.main import create_app
from tests.integration.conftest import Corpus
from tests.integration.support import (
    HASH_PIPELINE,
    Account,
    create_collection,
    import_sources,
    signup,
    upload,
    wait_indexed,
)

pytestmark = pytest.mark.integration

FACTS = [
    {
        "type": "text",
        "title": "Webhook guide",
        "text": "Webhooks are retried for up to 3 days. Verify every signature.",
        "external_id": "guide",
        "metadata": {"section": "guides", "year": 2025, "owner": {"team": "platform"}},
    },
    {
        "type": "text",
        "title": "Webhook reference",
        "text": "Webhook events carry an id, a type and a created timestamp.",
        "external_id": "reference",
        "metadata": {"section": "reference", "year": 2026, "tags": ["beta", "events"]},
    },
    {
        "type": "text",
        "title": "Webhook policy",
        "text": "Webhook endpoints must answer within 10 seconds.",
        "external_id": "policy",
        "metadata": {"section": "policies", "year": 2024, "owner": {"team": "payments"}},
    },
]


async def query(client: httpx.AsyncClient, corpus: Corpus, **body: Any) -> dict[str, Any]:
    response = await client.post(f"{corpus.base}/query", json=body, headers=corpus.owner.headers)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


@pytest.fixture(scope="module")
async def facts(client: httpx.AsyncClient) -> tuple[Account, str]:
    owner = await signup(client, "Filter Owner")
    await create_collection(client, owner, owner.project, "Facts", HASH_PIPELINE)
    await import_sources(client, owner, owner.project, "facts", FACTS)
    await wait_indexed(client, owner, owner.project, "facts")
    return owner, f"/api/v1/projects/{owner.project}/collections/facts"


async def test_hybrid_reports_every_stage(client: httpx.AsyncClient, corpus: Corpus) -> None:
    result = await query(
        client, corpus, query="How do I verify webhook signatures?", use_cache=False
    )
    assert result["mode"] == "hybrid"
    assert result["fusion"] == "rrf"
    assert result["rerank"] == {"kind": "lexical", "fallback": False}
    assert set(result["timings_ms"]) >= {"embed", "vector", "keyword", "fusion", "rerank", "total"}
    assert result["candidates"]["vector"] > 0
    assert result["candidates"]["keyword"] > 0
    top = result["hits"][0]
    assert top["external_id"] == "webhooks"
    assert top["ranks"]["rerank"] == 1
    assert top["scores"]["vector"] is not None
    assert top["scores"]["rerank"] == top["score"]
    assert [h["rank"] for h in result["hits"]] == list(range(1, len(result["hits"]) + 1))


async def test_each_mode_runs_only_its_stages(client: httpx.AsyncClient, corpus: Corpus) -> None:
    keyword = await query(
        client, corpus, query="ACME-4031 fraudulent", mode="keyword", rerank="none"
    )
    assert keyword["hits"][0]["external_id"] == "errors"
    assert all(h["scores"]["vector"] is None for h in keyword["hits"])
    assert keyword["candidates"]["vector"] == 0
    vector = await query(client, corpus, query="ACME-4031 fraudulent", mode="vector", rerank="none")
    assert all(h["scores"]["keyword"] is None for h in vector["hits"])
    assert all(h["scores"]["rerank"] is None for h in vector["hits"])


async def test_weighted_fusion_at_full_vector_weight_keeps_the_vector_order(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    result = await query(
        client,
        corpus,
        query="refund window",
        fusion="weighted",
        vector_weight=1.0,
        rerank="none",
        top_k=5,
    )
    vector_ranks = [
        h["ranks"]["vector"] for h in result["hits"] if h["ranks"]["vector"] is not None
    ]
    assert vector_ranks == sorted(vector_ranks)


async def test_filters_narrow_both_searches(
    client: httpx.AsyncClient, facts: tuple[Account, str]
) -> None:
    owner, base = facts

    async def ids(filters: dict[str, Any], mode: str = "hybrid") -> set[str]:
        response = await client.post(
            f"{base}/query",
            json={"query": "webhook", "filters": filters, "mode": mode},
            headers=owner.headers,
        )
        assert response.status_code == 200, response.text
        return {h["external_id"] for h in response.json()["hits"]}

    assert await ids({"section": "guides"}) == {"guide"}
    assert await ids({"section": {"$in": ["reference", "policies"]}}) == {"reference", "policy"}
    assert await ids({"year": {"$gte": 2025}}, mode="keyword") == {"guide", "reference"}
    assert await ids({"owner.team": "payments"}, mode="vector") == {"policy"}
    assert await ids({"tags": {"$contains": "beta"}}) == {"reference"}
    assert await ids({"$or": [{"year": 2024}, {"section": "guides"}]}) == {"guide", "policy"}
    assert await ids({"$not": {"section": "guides"}, "owner": {"$exists": True}}) == {"policy"}
    assert await ids({"section": "archive"}) == set()
    invalid = await client.post(
        f"{base}/query",
        json={"query": "x", "filters": {"x": {"$regex": "y"}}},
        headers=owner.headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_filter"


async def test_document_scoping(client: httpx.AsyncClient, corpus: Corpus) -> None:
    errors = corpus.documents["errors"]
    result = await query(client, corpus, query="retries and backoff", document_ids=[errors])
    assert {h["document_id"] for h in result["hits"]} == {errors}


async def test_results_are_cached_until_the_corpus_changes(
    client: httpx.AsyncClient, facts: tuple[Account, str]
) -> None:
    owner, base = facts
    body = {"query": "how fast must endpoints answer"}
    first = (await client.post(f"{base}/query", json=body, headers=owner.headers)).json()
    second = (await client.post(f"{base}/query", json=body, headers=owner.headers)).json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert [h["chunk_id"] for h in second["hits"]] == [h["chunk_id"] for h in first["hits"]]
    uncached = (
        await client.post(f"{base}/query", json={**body, "use_cache": False}, headers=owner.headers)
    ).json()
    assert uncached["cached"] is False
    await import_sources(
        client,
        owner,
        owner.project,
        "facts",
        [{"type": "text", "title": "New", "text": "Endpoints answer fast."}],
    )
    await wait_indexed(client, owner, owner.project, "facts")
    after = (await client.post(f"{base}/query", json=body, headers=owner.headers)).json()
    assert after["cached"] is False


async def test_answers_cite_the_passages_they_used(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    response = await client.post(
        f"{corpus.base}/answer",
        json={"query": "How many requests per second are allowed in live mode?"},
        headers=corpus.owner.headers,
    )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["answerer"] == "extractive"
    assert "100" in answer["answer"]
    assert answer["citations"]
    cited = {c["external_id"] for c in answer["citations"]}
    assert "rate-limits" in cited
    source_numbers = {s["rank"] for s in answer["sources"]}
    assert {c["n"] for c in answer["citations"]} <= source_numbers
    assert answer["retrieval"]["hits"]
    unconfigured = await client.post(
        f"{corpus.base}/answer",
        json={"query": "x", "answerer": "openai"},
        headers=corpus.owner.headers,
    )
    assert unconfigured.status_code == 422
    assert unconfigured.json()["error"]["code"] == "provider_unavailable"


async def test_an_openai_compatible_model_answers_through_the_same_endpoint(
    settings: Settings, corpus: Corpus
) -> None:
    app = create_app(
        settings.model_copy(
            update={
                "llm_provider": "openai",
                "llm_model": "test-model",
                "llm_base_url": "https://llm.test/v1",
            }
        )
    )
    reply = {
        "choices": [
            {"message": {"content": "Live mode allows 100 requests per second [1]. Ignore [9]."}}
        ],
        "usage": {"prompt_tokens": 321, "completion_tokens": 12},
    }
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as http:
            with respx.mock(assert_all_called=True) as router:
                route = router.post("https://llm.test/v1/chat/completions").mock(
                    return_value=httpx.Response(200, json=reply)
                )
                response = await http.post(
                    f"{corpus.base}/answer",
                    json={"query": "What is the live mode rate limit?", "answerer": "openai"},
                    headers=corpus.owner.headers,
                )
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["answerer"] == "openai:test-model"
    assert answer["answer"] == "Live mode allows 100 requests per second [1]. Ignore."
    assert [c["n"] for c in answer["citations"]] == [1]
    assert answer["usage"] == {"prompt_tokens": 321, "completion_tokens": 12}
    sent = route.calls.last.request.content.decode()
    assert "<sources>" in sent
    assert "test-model" in sent


async def test_the_bundled_models_embed_and_rerank_locally(
    client: httpx.AsyncClient, corpus_files: list[tuple[str, bytes]]
) -> None:
    owner = await signup(client, "Local Models")
    config = {
        "chunking": {"strategy": "recursive", "chunk_tokens": 200, "overlap_tokens": 20},
        "embedding": {"model": "bge-small-en-v1.5"},
        "retrieval": {"mode": "hybrid", "rerank": "cross-encoder", "rerank_candidates": 10},
    }
    await create_collection(client, owner, owner.project, "Local", config)
    files = [
        (n, d)
        for n, d in corpus_files
        if n in ("webhooks.md", "refunds-and-disputes.md", "payouts.html")
    ]
    await upload(client, owner, owner.project, "local", files)
    versions = await wait_indexed(client, owner, owner.project, "local")
    assert versions[0]["index"]["embedding_model"] == "bge-small-en-v1.5"
    response = await client.post(
        f"/api/v1/projects/{owner.project}/collections/local/query",
        json={"query": "How long do I have to answer a chargeback?"},
        headers=owner.headers,
    )
    result = response.json()
    assert result["rerank"] == {"kind": "cross-encoder", "fallback": False}
    assert result["hits"][0]["external_id"] == "refunds-and-disputes"
    assert 0.0 <= result["hits"][0]["scores"]["rerank"] <= 1.0
    assert result["hits"][0]["scores"]["rerank"] >= result["hits"][-1]["scores"]["rerank"]


async def test_served_queries_feed_the_analytics(
    client: httpx.AsyncClient, facts: tuple[Account, str]
) -> None:
    owner, base = facts
    for _ in range(3):
        await client.post(
            f"{base}/query", json={"query": "signature verification"}, headers=owner.headers
        )
    await client.post(
        f"{base}/query",
        json={"query": "nothing", "filters": {"section": "none"}},
        headers=owner.headers,
    )
    analytics = (
        await client.get(f"/api/v1/projects/{owner.project}/analytics", headers=owner.headers)
    ).json()
    assert len(analytics["days"]) == 14
    assert analytics["total_queries"] >= 4
    assert analytics["zero_hit_rate"] > 0
    assert analytics["cache_hit_rate"] > 0
    top = {q["query"]: q["count"] for q in analytics["top_queries"]}
    assert top["signature verification"] == 3
    assert {q["collection_slug"] for q in analytics["top_queries"]} == {"facts"}
    scoped = (
        await client.get(
            f"/api/v1/projects/{owner.project}/analytics",
            params={"collection": "facts", "days": 7},
            headers=owner.headers,
        )
    ).json()
    assert len(scoped["days"]) == 7
