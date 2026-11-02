"""Ingestion: every loader and format, originals in S3, deduplication, the URL fetcher,
metadata, deletion and reprocessing."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from tests.integration.conftest import AwsResources, Corpus, aws_client
from tests.integration.support import (
    HASH_PIPELINE,
    create_collection,
    import_sources,
    signup,
    upload,
    wait_indexed,
)

pytestmark = pytest.mark.integration

PAGES = {
    "/guide.html": (
        "text/html; charset=utf-8",
        b"<html><head><title>Sandbox guide</title></head><body><nav>Home</nav>"
        b"<h1>Sandbox guide</h1><p>The sandbox resets every Sunday at 02:00 UTC.</p>"
        b"<h2>Limits</h2><p>Sandbox accounts can create 500 payments per day.</p></body></html>",
    ),
    "/notes.md": (
        "text/plain",
        b"# Notes\n\n## Tips\n\nUse a fresh idempotency key per request.\n",
    ),
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/old":
            self.send_response(301)
            self.send_header("location", "/guide.html")
            self.end_headers()
            return
        page = PAGES.get(self.path)
        if page is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("content-type", page[0])
        self.send_header("content-length", str(len(page[1])))
        self.end_headers()
        self.wfile.write(page[1])

    def log_message(self, *_: object) -> None:
        return None


@pytest.fixture(scope="module")
def website() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def test_every_format_is_parsed_and_indexed(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    documents = (
        await client.get(
            f"{corpus.base}/documents", params={"limit": 100}, headers=corpus.owner.headers
        )
    ).json()
    by_id = {d["external_id"]: d for d in documents["items"]}
    assert {d["kind"] for d in by_id.values()} >= {"pdf", "docx", "md", "html", "txt", "csv"}
    assert all(d["status"] == "ready" for d in by_id.values())
    assert by_id["service-level-agreement"]["title"] == "Service Level Agreement"
    assert by_id["security-and-compliance-overview"]["section_count"] >= 5
    pdf = (
        await client.get(
            f"{corpus.base}/documents/{corpus.documents['service-level-agreement']}",
            headers=corpus.owner.headers,
        )
    ).json()
    assert [s["label"] for s in pdf["sections"]] == ["Page 1", "Page 2", "Page 3"]
    # Other tests may add versions that share this index; version 1 always reads it.
    assert 1 in pdf["indexes"][0]["pipeline_versions"]
    assert pdf["indexes"][0]["status"] == "ready"
    assert pdf["indexes"][0]["chunk_count"] > 0


async def test_originals_are_kept_in_s3_with_kms(
    client: httpx.AsyncClient,
    corpus: Corpus,
    aws: AwsResources,
    corpus_files: list[tuple[str, bytes]],
) -> None:
    document_id = corpus.documents["errors"]
    original = await client.get(
        f"{corpus.base}/documents/{document_id}/file", headers=corpus.owner.headers
    )
    assert original.status_code == 200
    assert original.content == dict(corpus_files)["errors.md"]
    keys = [
        item["Key"]
        for item in aws_client("s3").list_objects_v2(Bucket=aws.bucket).get("Contents", [])
        if document_id in item["Key"]
    ]
    assert len(keys) == 1
    assert keys[0].startswith("projects/")
    head = aws_client("s3").head_object(Bucket=aws.bucket, Key=keys[0])
    assert head["ServerSideEncryption"] == "aws:kms"


async def test_duplicates_and_bad_files_are_reported_per_file(
    client: httpx.AsyncClient, corpus: Corpus, corpus_files: list[tuple[str, bytes]]
) -> None:
    files = dict(corpus_files)
    result = await upload(
        client,
        corpus.owner,
        corpus.project,
        corpus.collection,
        [
            ("errors.md", files["errors.md"]),
            ("tool.exe", b"MZ\x90\x00"),
            ("fake.pdf", b"not a pdf at all"),
            ("empty.txt", b""),
        ],
    )
    assert [d["external_id"] for d in result["duplicates"]] == ["errors"]
    assert {r["name"]: r["code"] for r in result["rejected"]} == {
        "tool.exe": "unsupported_media_type",
        "fake.pdf": "content_mismatch",
        "empty.txt": "empty_file",
    }
    assert result["created"] == []


async def test_text_sources_keep_their_external_ids(client: httpx.AsyncClient) -> None:
    owner = await signup(client, "Text Loader")
    await create_collection(client, owner, owner.project, "Notes", HASH_PIPELINE)
    note = {
        "type": "text",
        "title": "Escalation",
        "text": "Page on-call within 10 minutes.",
        "external_id": "escalation",
    }
    first = await import_sources(client, owner, owner.project, "notes", [note])
    assert [d["external_id"] for d in first["created"]] == ["escalation"]
    again = await import_sources(client, owner, owner.project, "notes", [note])
    assert again["rejected"][0]["code"] == "duplicate_external_id"
    same_text = await import_sources(
        client, owner, owner.project, "notes", [{**note, "external_id": None, "title": "Copy"}]
    )
    assert [d["external_id"] for d in same_text["duplicates"]] == ["escalation"]
    bad = await client.post(
        f"/api/v1/projects/{owner.project}/collections/notes/documents/import",
        json={"items": [{**note, "external_id": "x", "metadata": {"bad key": 1}}]},
        headers=owner.headers,
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_metadata"


async def test_a_title_someone_gave_survives_parsing_and_a_made_up_one_does_not(
    client: httpx.AsyncClient, website: str
) -> None:
    """A heading inside a source must not rename a document a person titled. A file or an
    address nobody titled takes the title its content declares."""
    owner = await signup(client, "Titles")
    await create_collection(client, owner, owner.project, "Notes", HASH_PIPELINE)
    await import_sources(
        client,
        owner,
        owner.project,
        "notes",
        [
            {
                "type": "text",
                "title": "Payout holds FAQ",
                "format": "markdown",
                "text": "# Payout holds\n\nA payout is held for review when bank details change.",
            },
            {"type": "url", "url": f"{website}/notes.md", "title": "Tips and tricks"},
            {"type": "url", "url": f"{website}/old"},
        ],
    )
    await upload(
        client,
        owner,
        owner.project,
        "notes",
        [("release-notes.md", b"# Release notes 2026\n\nThe sandbox resets every week.\n")],
    )
    await wait_indexed(client, owner, owner.project, "notes")
    listing = await client.get(
        f"/api/v1/projects/{owner.project}/collections/notes/documents",
        params={"limit": 100},
        headers=owner.headers,
    )
    titles = {d["title"] for d in listing.json()["items"]}
    assert titles == {"Payout holds FAQ", "Tips and tricks", "Sandbox guide", "Release notes 2026"}


async def test_url_sources_are_fetched_snapshotted_and_searchable(
    client: httpx.AsyncClient, website: str
) -> None:
    owner = await signup(client, "URL Loader")
    await create_collection(client, owner, owner.project, "Web", HASH_PIPELINE)
    base = f"/api/v1/projects/{owner.project}/collections/web"
    result = await import_sources(
        client,
        owner,
        owner.project,
        "web",
        [
            {"type": "url", "url": f"{website}/old", "metadata": {"section": "sandbox"}},
            {"type": "url", "url": f"{website}/notes.md"},
            {"type": "url", "url": f"{website}/missing"},
        ],
    )
    assert len(result["created"]) == 3
    await wait_indexed(client, owner, owner.project, "web")
    documents = {
        d["source_uri"]: d
        for d in (await client.get(f"{base}/documents", headers=owner.headers)).json()["items"]
    }
    guide = documents[f"{website}/old"]
    assert guide["status"] == "ready"
    assert guide["kind"] == "html"
    assert guide["title"] == "Sandbox guide"
    assert documents[f"{website}/notes.md"]["kind"] == "md"
    missing = documents[f"{website}/missing"]
    assert missing["status"] == "failed"
    assert "404" in missing["error"]
    snapshot = await client.get(f"{base}/documents/{guide['id']}/file", headers=owner.headers)
    assert b"resets every Sunday" in snapshot.content
    hits = (
        await client.post(
            f"{base}/query", json={"query": "when does the sandbox reset"}, headers=owner.headers
        )
    ).json()["hits"]
    assert hits[0]["external_id"] == guide["external_id"]
    assert hits[0]["metadata"] == {"section": "sandbox"}


async def test_metadata_changes_reach_the_chunks_without_a_rebuild(
    client: httpx.AsyncClient, corpus: Corpus
) -> None:
    document_id = corpus.documents["python-sdk"]
    query = {"query": "python sdk retries", "filters": {"tier": "beta"}}
    before = (
        await client.post(f"{corpus.base}/query", json=query, headers=corpus.owner.headers)
    ).json()
    assert before["hits"] == []
    updated = await client.patch(
        f"{corpus.base}/documents/{document_id}",
        json={"metadata": {"section": "reference", "tier": "beta"}},
        headers=corpus.owner.headers,
    )
    assert updated.status_code == 200
    after = (
        await client.post(f"{corpus.base}/query", json=query, headers=corpus.owner.headers)
    ).json()
    assert {hit["external_id"] for hit in after["hits"]} == {"python-sdk"}


async def test_deleting_a_document_removes_its_chunks_and_original(
    client: httpx.AsyncClient, aws: AwsResources
) -> None:
    owner = await signup(client, "Deleter")
    await create_collection(client, owner, owner.project, "Scratch", HASH_PIPELINE)
    base = f"/api/v1/projects/{owner.project}/collections/scratch"
    created = (
        await upload(
            client,
            owner,
            owner.project,
            "scratch",
            [("memo.md", b"# Memo\n\nThe vault code is 4417.\n")],
        )
    )["created"][0]
    await wait_indexed(client, owner, owner.project, "scratch")
    chunks = (await client.get(f"{base}/pipelines/1/chunks", headers=owner.headers)).json()
    assert chunks["total"] > 0

    assert (
        await client.delete(f"{base}/documents/{created['id']}", headers=owner.headers)
    ).status_code == 204
    chunks = (await client.get(f"{base}/pipelines/1/chunks", headers=owner.headers)).json()
    assert chunks["total"] == 0
    left = (
        aws_client("s3").list_objects_v2(Bucket=aws.bucket, Prefix="projects/").get("Contents", [])
    )
    assert not [o for o in left if created["id"] in o["Key"]]


async def test_reprocessing_parses_again_and_rebuilds_every_index(
    client: httpx.AsyncClient,
) -> None:
    owner = await signup(client, "Reprocessor")
    await create_collection(client, owner, owner.project, "Again", HASH_PIPELINE)
    base = f"/api/v1/projects/{owner.project}/collections/again"
    created = (
        await upload(
            client,
            owner,
            owner.project,
            "again",
            [("a.md", b"# A\n\nAlpha bravo charlie delta.\n")],
        )
    )["created"][0]
    await wait_indexed(client, owner, owner.project, "again")
    response = await client.post(
        f"{base}/documents/{created['id']}/reprocess", headers=owner.headers
    )
    assert response.status_code == 200
    await wait_indexed(client, owner, owner.project, "again")
    detail = (await client.get(f"{base}/documents/{created['id']}", headers=owner.headers)).json()
    assert detail["status"] == "ready"
    assert [entry["status"] for entry in detail["indexes"]] == ["ready"]
