from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import respx

BASE = "http://ragkit.test"
PROJECT = "/api/v1/projects/acme-payments"


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAGKIT_URL", BASE)
    monkeypatch.setenv("RAGKIT_API_KEY", "rgk_testprefix_secret")
    monkeypatch.setenv("RAGKIT_PROJECT", "acme-payments")


def run_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "run-1",
        "label": "v2 recursive, hybrid + cross-encoder",
        "status": "completed",
        "dataset": {"id": "d1", "slug": "smoke", "name": "Smoke test"},
        "collection": {"id": "c1", "slug": "developer-docs", "name": "Developer docs"},
        "pipeline_version": 2,
        "k": 5,
        "grader": "deterministic",
        "total_items": 8,
        "completed_items": 8,
        "metrics": {"means": {"hit_rate": 0.95, "mrr": 0.81}},
        "error": None,
        "is_baseline": False,
        "created_at": "2026-10-30T10:00:00Z",
        "duration_ms": 9000,
    }
    body.update(overrides)
    return body


def hit_body(rank: int = 1) -> dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": f"chunk-{rank}",
        "document_id": "doc-1",
        "document_title": "Webhooks",
        "external_id": "webhooks",
        "location": "Verifying signatures",
        "heading": "Webhooks > Verifying signatures",
        "text": "Compute an HMAC-SHA256 of the timestamp and the raw body.",
        "context": None,
        "metadata": {"section": "guides"},
        "score": 0.91,
        "scores": {"vector": 0.82, "keyword": 0.4, "fused": 0.03, "rerank": 0.91},
        "ranks": {"vector": 1, "keyword": 2, "fused": 1, "rerank": 1},
    }
