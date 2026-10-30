"""Who can do what: project isolation, roles, API keys, sessions and CSRF."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import WEB_ORIGIN, Corpus
from tests.integration.support import (
    HASH_PIPELINE,
    PASSWORD,
    add_member,
    bearer,
    create_api_key,
    create_collection,
    import_sources,
    signup,
    wait_run,
)

pytestmark = pytest.mark.integration

SWEEP_ITEM = {
    "question": "How long are idempotency results saved?",
    "expected_sources": [{"document": "idempotency", "evidence": "saved for 24 hours"}],
    "expected_answer": "24 hours.",
}


async def test_outsiders_get_not_found_for_every_project_route(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    owner = corpus.owner
    project = f"/api/v1/projects/{corpus.project}"
    dataset = await client.post(
        f"{project}/datasets",
        json={"name": "Sweep", "collection": corpus.collection, "items": [SWEEP_ITEM]},
        headers=owner.headers,
    )
    assert dataset.status_code == 201, dataset.text
    run = (
        await client.post(f"{project}/eval-runs", json={"dataset": "sweep"}, headers=owner.headers)
    ).json()
    await wait_run(client, owner, corpus.project, run["id"])
    key = await create_api_key(client, owner, corpus.project)
    document = corpus.documents["webhooks"]
    item = (await client.get(f"{project}/datasets/sweep/items", headers=owner.headers)).json()
    item_id = item["items"][0]["id"]
    base = corpus.base
    outsider = await signup(client, "Outsider")

    probes: list[tuple[str, str, object]] = [
        ("GET", project, None),
        ("PATCH", project, {"name": "Taken over"}),
        ("DELETE", project, None),
        ("GET", f"{project}/members", None),
        ("POST", f"{project}/members", {"email": outsider.email, "role": "owner"}),
        ("PATCH", f"{project}/members/{owner.user_id}", {"role": "viewer"}),
        ("DELETE", f"{project}/members/{owner.user_id}", None),
        ("GET", f"{project}/activity", None),
        ("GET", f"{project}/analytics", None),
        ("GET", f"{project}/api-keys", None),
        ("POST", f"{project}/api-keys", {"name": "Exfiltrate"}),
        ("DELETE", f"{project}/api-keys/{key['id']}", None),
        ("GET", f"{project}/collections", None),
        ("POST", f"{project}/collections", {"name": "Mine now"}),
        ("GET", base, None),
        ("PATCH", base, {"name": "Renamed"}),
        ("DELETE", base, None),
        ("GET", f"{base}/documents", None),
        (
            "POST",
            f"{base}/documents/import",
            {"items": [{"type": "text", "title": "t", "text": "x"}]},
        ),
        ("GET", f"{base}/documents/{document}", None),
        ("GET", f"{base}/documents/{document}/file", None),
        ("PATCH", f"{base}/documents/{document}", {"title": "Renamed"}),
        ("POST", f"{base}/documents/{document}/reprocess", None),
        ("DELETE", f"{base}/documents/{document}", None),
        ("GET", f"{base}/pipelines", None),
        ("POST", f"{base}/pipelines", {"name": "Hijack", "config": HASH_PIPELINE}),
        ("POST", f"{base}/pipelines/preview", {"text": "# T\n\nBody text."}),
        ("GET", f"{base}/pipelines/1", None),
        ("POST", f"{base}/pipelines/1/activate", None),
        ("GET", f"{base}/pipelines/1/chunks", None),
        ("GET", f"{base}/pipelines/1/chunks/stats", None),
        ("POST", f"{base}/query", {"query": "webhook signatures"}),
        ("POST", f"{base}/answer", {"query": "webhook signatures"}),
        ("GET", f"{project}/datasets", None),
        ("POST", f"{project}/datasets", {"name": "x", "collection": corpus.collection}),
        ("GET", f"{project}/datasets/sweep", None),
        ("PATCH", f"{project}/datasets/sweep", {"name": "x"}),
        ("DELETE", f"{project}/datasets/sweep", None),
        ("GET", f"{project}/datasets/sweep/items", None),
        ("POST", f"{project}/datasets/sweep/items", {"items": [SWEEP_ITEM]}),
        ("GET", f"{project}/datasets/sweep/export", None),
        ("DELETE", f"{project}/datasets/sweep/items/{item_id}", None),
        ("GET", f"{project}/eval-runs", None),
        ("POST", f"{project}/eval-runs", {"dataset": "sweep"}),
        ("GET", f"{project}/eval-runs/{run['id']}", None),
        ("GET", f"{project}/eval-runs/{run['id']}/results", None),
        ("GET", f"{project}/eval-runs/compare?ids={run['id']},{run['id']}", None),
        ("POST", f"{project}/eval-runs/{run['id']}/gate", {}),
        ("POST", f"{project}/eval-runs/{run['id']}/baseline", None),
        ("DELETE", f"{project}/eval-runs/{run['id']}", None),
    ]
    for method, path, body in probes:
        response = await client.request(method, path, json=body, headers=outsider.headers)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
        assert response.json()["error"]["code"] == "not_found"

    still_there = await client.get(f"{base}/documents/{document}", headers=owner.headers)
    assert still_there.status_code == 200


async def test_ids_from_another_project_resolve_to_nothing(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    other = await signup(client, "Other Owner")
    await create_collection(client, other, other.project, "Mine", HASH_PIPELINE)
    base = f"/api/v1/projects/{other.project}/collections/mine"
    document = corpus.documents["webhooks"]

    detail = await client.get(f"{base}/documents/{document}", headers=other.headers)
    chunks = await client.get(
        f"{base}/pipelines/1/chunks", params={"document_id": document}, headers=other.headers
    )
    scoped = await client.post(
        f"{base}/query",
        json={"query": "webhook signatures", "document_ids": [document]},
        headers=other.headers,
    )

    assert detail.status_code == 404
    assert chunks.json()["items"] == []
    assert scoped.json()["hits"] == []


async def test_roles_decide_who_reads_who_builds_and_who_manages(
    client: httpx.AsyncClient,
) -> None:
    owner = await signup(client, "Owner")
    editor = await signup(client, "Editor")
    viewer = await signup(client, "Viewer")
    project = owner.project
    await add_member(client, owner, project, editor, "editor")
    await add_member(client, owner, project, viewer, "viewer")
    await create_collection(client, owner, project, "Notes", HASH_PIPELINE)
    base = f"/api/v1/projects/{project}/collections/notes"
    note = {"type": "text", "title": "Refunds", "text": "Refunds take five business days."}

    denied = await client.post(
        f"{base}/documents/import", json={"items": [note]}, headers=viewer.headers
    )
    assert denied.status_code == 403
    assert (
        await client.post(f"{base}/query", json={"query": "refunds"}, headers=viewer.headers)
    ).status_code == 200

    await import_sources(client, editor, project, "notes", [note])
    for method, path, body in [
        ("POST", f"/api/v1/projects/{project}/members", {"email": "x@example.com"}),
        ("GET", f"/api/v1/projects/{project}/api-keys", None),
        ("DELETE", base, None),
        ("PATCH", f"/api/v1/projects/{project}", {"name": "Mine"}),
    ]:
        response = await client.request(method, path, json=body, headers=editor.headers)
        assert response.status_code == 403, f"{method} {path}"
        assert response.json()["error"]["code"] == "forbidden"

    last_owner = await client.patch(
        f"/api/v1/projects/{project}/members/{owner.user_id}",
        json={"role": "editor"},
        headers=owner.headers,
    )
    assert last_owner.status_code == 422
    assert last_owner.json()["error"]["code"] == "last_owner"


async def test_api_keys_carry_a_role_and_stop_working_when_revoked(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    viewer_key = await create_api_key(client, corpus.owner, corpus.project, "viewer")
    editor_key = await create_api_key(client, corpus.owner, corpus.project, "editor")
    base = corpus.base
    note = {"items": [{"type": "text", "title": "Key note", "text": "Written with an API key."}]}

    query = await client.post(
        f"{base}/query", json={"query": "rate limits"}, headers=bearer(viewer_key["key"])
    )
    assert query.status_code == 200
    blocked = await client.post(
        f"{base}/documents/import", json=note, headers=bearer(viewer_key["key"])
    )
    assert blocked.status_code == 403
    written = await client.post(
        f"{base}/documents/import", json=note, headers=bearer(editor_key["key"])
    )
    assert written.status_code == 201
    people_only = await client.get("/api/v1/auth/me", headers=bearer(editor_key["key"]))
    assert people_only.status_code == 403

    other = await signup(client, "Key Prober")
    foreign = await client.get(
        f"/api/v1/projects/{other.project}/collections", headers=bearer(viewer_key["key"])
    )
    assert foreign.status_code == 404

    revoked = await client.delete(
        f"/api/v1/projects/{corpus.project}/api-keys/{viewer_key['id']}",
        headers=corpus.owner.headers,
    )
    assert revoked.status_code == 204
    after = await client.post(
        f"{base}/query", json={"query": "x"}, headers=bearer(viewer_key["key"])
    )
    assert after.status_code == 401
    assert after.json()["error"]["code"] == "invalid_api_key"
    garbage = await client.get(f"{base}", headers=bearer("rgk_notakey_" + "x" * 43))
    assert garbage.status_code == 401


async def test_cookie_sessions_need_a_same_site_origin_for_writes(
    client: httpx.AsyncClient,
) -> None:
    person = await signup(client, "Cookie Person")
    login = await client.post(
        "/api/v1/auth/login", json={"email": person.email, "password": PASSWORD}
    )
    assert login.status_code == 200
    try:
        reads = await client.get("/api/v1/auth/me")
        assert reads.status_code == 200
        forged = await client.post(
            "/api/v1/projects", json={"name": "CSRF"}, headers={"origin": "https://evil.example"}
        )
        assert forged.status_code == 403
        assert forged.json()["error"]["code"] == "csrf"
        allowed = await client.post(
            "/api/v1/projects", json={"name": "Legit"}, headers={"origin": WEB_ORIGIN}
        )
        assert allowed.status_code == 201
        logout = await client.post("/api/v1/auth/logout", headers={"origin": WEB_ORIGIN})
        assert logout.status_code == 204
        assert (
            await client.get("/api/v1/auth/me", headers=bearer(login.json()["token"]))
        ).status_code == 401
    finally:
        client.cookies.clear()


async def test_sign_in_errors_are_uniform(client: httpx.AsyncClient) -> None:
    person = await signup(client, "Sign In")
    wrong = await client.post(
        "/api/v1/auth/login", json={"email": person.email, "password": "wrong-password-1"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"] == "invalid_credentials"
    client.cookies.clear()
