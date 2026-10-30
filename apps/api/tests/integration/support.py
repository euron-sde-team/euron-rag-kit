"""HTTP helpers shared by the integration tests."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

PASSWORD = "Integration-pass-2026"

# Fast and deterministic: hash embeddings, structure-aware chunks, hybrid with the lexical
# reranker. Tests of the bundled models build their own versions.
HASH_PIPELINE: dict[str, Any] = {
    "cleaning": {"strip_boilerplate": True},
    "chunking": {"strategy": "recursive", "chunk_tokens": 160, "overlap_tokens": 20},
    "embedding": {"model": "hash-384"},
    "retrieval": {"mode": "hybrid", "rerank": "lexical", "top_k": 5},
}


@dataclass(frozen=True)
class Account:
    email: str
    user_id: str
    token: str
    project: str  # slug of the personal project created at sign-up

    @property
    def headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}"}


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


async def signup(client: httpx.AsyncClient, name: str = "Test Person") -> Account:
    email = f"{uuid.uuid4().hex[:12]}@example.com"
    response = await client.post(
        "/api/v1/auth/signup", json={"email": email, "name": name, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    token = response.json()["token"]
    # Bearer tokens only: a cookie left in the shared client would authenticate later calls.
    client.cookies.clear()
    me = (await client.get("/api/v1/auth/me", headers=bearer(token))).json()
    return Account(email, me["user"]["id"], token, me["projects"][0]["slug"])


async def add_member(
    client: httpx.AsyncClient, owner: Account, project: str, member: Account, role: str
) -> None:
    response = await client.post(
        f"/api/v1/projects/{project}/members",
        json={"email": member.email, "role": role},
        headers=owner.headers,
    )
    assert response.status_code == 201, response.text


async def create_api_key(
    client: httpx.AsyncClient, owner: Account, project: str, role: str = "viewer"
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project}/api-keys",
        json={"name": f"{role} key", "role": role},
        headers=owner.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def create_collection(
    client: httpx.AsyncClient,
    account: Account,
    project: str,
    name: str,
    pipeline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name}
    if pipeline is not None:
        body["pipeline"] = pipeline
    response = await client.post(
        f"/api/v1/projects/{project}/collections", json=body, headers=account.headers
    )
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


async def upload(
    client: httpx.AsyncClient,
    account: Account,
    project: str,
    collection: str,
    files: list[tuple[str, bytes]],
    metadata: str | None = None,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project}/collections/{collection}/documents",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
        data={"metadata": metadata} if metadata else None,
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def import_sources(
    client: httpx.AsyncClient,
    account: Account,
    project: str,
    collection: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/projects/{project}/collections/{collection}/documents/import",
        json={"items": items},
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def wait_indexed(
    client: httpx.AsyncClient,
    account: Account,
    project: str,
    collection: str,
    timeout_s: float = 240,
) -> list[dict[str, Any]]:
    """Poll until no document is waiting and every version's index has settled."""
    base = f"/api/v1/projects/{project}/collections/{collection}"
    deadline = time.monotonic() + timeout_s
    while True:
        documents = (
            await client.get(f"{base}/documents", params={"limit": 100}, headers=account.headers)
        ).json()["items"]
        versions = (await client.get(f"{base}/pipelines", headers=account.headers)).json()
        busy = [d for d in documents if d["status"] in ("queued", "processing")]
        building = [v for v in versions if v["index"]["status"] == "building"]
        if not busy and not building:
            return list(versions)
        if time.monotonic() > deadline:
            raise AssertionError(f"not indexed in time: {busy} {building}")
        await asyncio.sleep(0.3)


async def wait_run(
    client: httpx.AsyncClient, account: Account, project: str, run_id: str, timeout_s: float = 300
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        run: dict[str, Any] = (
            await client.get(
                f"/api/v1/projects/{project}/eval-runs/{run_id}", headers=account.headers
            )
        ).json()
        if run["status"] in ("completed", "failed"):
            return run
        if time.monotonic() > deadline:
            raise AssertionError(f"run not finished in time: {run['status']}")
        await asyncio.sleep(0.3)
