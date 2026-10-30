"""Pipeline versions: immutability, index reuse by fingerprint, activation, chunks, previews."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.integration.support import (
    HASH_PIPELINE,
    Account,
    create_collection,
    signup,
    upload,
    wait_indexed,
)

pytestmark = pytest.mark.integration
FILES = ("webhooks.md", "rate-limits.md", "Service Level Agreement.pdf", "pricing.csv")


@pytest.fixture(scope="module")
async def lab(
    client: httpx.AsyncClient, corpus_files: list[tuple[str, bytes]]
) -> tuple[Account, str]:
    owner = await signup(client, "Pipeline Lab")
    await create_collection(client, owner, owner.project, "Lab", HASH_PIPELINE)
    files = [(name, data) for name, data in corpus_files if name in FILES]
    await upload(client, owner, owner.project, "lab", files)
    await wait_indexed(client, owner, owner.project, "lab")
    return owner, f"/api/v1/projects/{owner.project}/collections/lab"


async def create_version(
    client: httpx.AsyncClient,
    owner: Account,
    base: str,
    name: str,
    config: dict[str, Any],
    **extra: Any,
) -> httpx.Response:
    return await client.post(
        f"{base}/pipelines", json={"name": name, "config": config, **extra}, headers=owner.headers
    )


async def test_retrieval_changes_share_the_index_and_need_no_rebuild(
    client: httpx.AsyncClient, lab: tuple[Account, str]
) -> None:
    owner, base = lab
    v1 = (await client.get(f"{base}/pipelines/1", headers=owner.headers)).json()
    response = await create_version(
        client, owner, base, "Vector only", {**HASH_PIPELINE, "retrieval": {"mode": "vector"}}
    )
    assert response.status_code == 201, response.text
    v2 = response.json()
    assert v2["index"]["id"] == v1["index"]["id"]
    assert v2["index"]["status"] == "ready"
    assert v2["index"]["shared_with"] == [1]
    assert v2["active"] is False
    assert v2["config"]["retrieval"]["mode"] == "vector"


async def test_index_changes_build_a_new_index_in_the_background(
    client: httpx.AsyncClient, lab: tuple[Account, str]
) -> None:
    owner, base = lab
    response = await create_version(
        client,
        owner,
        base,
        "Sentence windows",
        {
            **HASH_PIPELINE,
            "chunking": {
                "strategy": "sentence_window",
                "sentences_per_chunk": 1,
                "window_sentences": 1,
            },
        },
    )
    created = response.json()
    v1 = (await client.get(f"{base}/pipelines/1", headers=owner.headers)).json()
    assert created["index"]["id"] != v1["index"]["id"]
    versions = await wait_indexed(client, owner, owner.project, "lab")
    windows = next(v for v in versions if v["version"] == created["version"])
    assert windows["index"]["status"] == "ready"
    assert windows["index"]["progress"]["ready"] == len(FILES)
    assert windows["index"]["chunk_count"] > v1["index"]["chunk_count"]
    chunks = (
        await client.get(
            f"{base}/pipelines/{created['version']}/chunks",
            params={"limit": 200},
            headers=owner.headers,
        )
    ).json()
    assert any(c["context"] and c["text"] in c["context"] for c in chunks["items"])
    stats = (
        await client.get(
            f"{base}/pipelines/{created['version']}/chunks/stats", headers=owner.headers
        )
    ).json()
    assert stats["count"] == windows["index"]["chunk_count"]
    assert sum(bucket["count"] for bucket in stats["histogram"]) == stats["count"]


async def test_activation_switches_what_queries_use(
    client: httpx.AsyncClient, lab: tuple[Account, str]
) -> None:
    owner, base = lab
    created = (
        await create_version(
            client,
            owner,
            base,
            "Keyword",
            {**HASH_PIPELINE, "retrieval": {"mode": "keyword"}},
            activate=True,
        )
    ).json()
    assert created["active"] is True
    collection = (await client.get(base, headers=owner.headers)).json()
    assert collection["active_version"] == created["version"]
    result = (
        await client.post(f"{base}/query", json={"query": "webhook retries"}, headers=owner.headers)
    ).json()
    assert result["pipeline_version"] == created["version"]
    assert result["mode"] == "keyword"
    pinned = (
        await client.post(
            f"{base}/query",
            json={"query": "webhook retries", "pipeline_version": 1},
            headers=owner.headers,
        )
    ).json()
    assert pinned["pipeline_version"] == 1
    back = await client.post(f"{base}/pipelines/1/activate", headers=owner.headers)
    assert back.json()["active"] is True


@pytest.mark.parametrize(
    ("config", "code"),
    [
        ({"embedding": {"model": "no-such-model"}}, "invalid_pipeline"),
        (
            {"embedding": {"provider": "openai", "model": "text-embedding-3-large", "dim": 1024}},
            "provider_unavailable",
        ),
        ({"embedding": {"provider": "ollama", "model": "x", "dim": 999}}, "invalid_pipeline"),
        ({"answer": {"answerer": "openai"}}, "provider_unavailable"),
        ({"chunking": {"chunk_tokens": 100, "overlap_tokens": 90}}, "validation_failed"),
        ({"retrieval": {"modes": "vector"}}, "validation_failed"),
    ],
)
async def test_unusable_configurations_are_refused(
    client: httpx.AsyncClient, lab: tuple[Account, str], config: dict[str, Any], code: str
) -> None:
    owner, base = lab
    response = await create_version(client, owner, base, "Bad", config)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


async def test_previews_chunk_without_persisting(
    client: httpx.AsyncClient, lab: tuple[Account, str]
) -> None:
    owner, base = lab
    text = "# Guide\n\n" + " ".join(f"Sentence {i} explains a rule." for i in range(60))
    fixed = (
        await client.post(
            f"{base}/pipelines/preview",
            json={
                "chunking": {"strategy": "fixed", "chunk_tokens": 64, "overlap_tokens": 0},
                "text": text,
            },
            headers=owner.headers,
        )
    ).json()
    assert fixed["stats"]["count"] >= 4
    assert fixed["stats"]["max_tokens"] <= 70
    documents = (await client.get(f"{base}/documents", headers=owner.headers)).json()["items"]
    sla = next(d for d in documents if d["kind"] == "pdf")
    cleaned = (
        await client.post(
            f"{base}/pipelines/preview",
            json={"cleaning": {"strip_boilerplate": True}, "document_id": sla["id"]},
            headers=owner.headers,
        )
    ).json()
    assert cleaned["cleaning"]["boilerplate_blocks"] >= 4
    assert not any("Confidential. Page" in c["text"] for c in cleaned["chunks"])
    versions = (await client.get(f"{base}/pipelines", headers=owner.headers)).json()
    assert all(v["name"] != "preview" for v in versions)
    missing = await client.get(f"{base}/pipelines/99", headers=owner.headers)
    assert missing.status_code == 404
