"""The Python SDK and its CLI against a real server (uvicorn on a free port)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from ragkit import RAGKit
from ragkit.cli import app as cli
from typer.testing import CliRunner

from ragkit_server.core.config import Settings
from ragkit_server.main import create_app
from tests.integration.support import HASH_PIPELINE, PASSWORD

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def server(settings: Settings) -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/livez", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield url
    instance.should_exit = True
    thread.join(timeout=30)


@pytest.fixture(scope="module")
def project_key(server: str) -> tuple[str, str]:
    """A fresh account, its project and an editor key, made over plain HTTP."""
    email = f"sdk-{time.time_ns()}@example.com"
    signup = httpx.post(
        f"{server}/api/v1/auth/signup",
        json={"email": email, "name": "SDK User", "password": PASSWORD},
    )
    token = signup.json()["token"]
    headers = {"authorization": f"Bearer {token}"}
    project = httpx.get(f"{server}/api/v1/auth/me", headers=headers).json()["projects"][0]["slug"]
    httpx.post(
        f"{server}/api/v1/projects/{project}/collections",
        json={"name": "Docs", "pipeline": HASH_PIPELINE},
        headers=headers,
    )
    key = httpx.post(
        f"{server}/api/v1/projects/{project}/api-keys",
        json={"name": "CI", "role": "editor"},
        headers=headers,
    )
    return project, key.json()["key"]


def test_the_sdk_ingests_queries_answers_and_evaluates(
    server: str, project_key: tuple[str, str], samples_dir: Path, tmp_path: Path
) -> None:
    project, key = project_key
    with RAGKit(server, key, project) as rk:
        docs = rk.collection("docs")
        files = [
            samples_dir / "corpus" / "developer-docs" / name
            for name in ("webhooks.md", "rate-limits.md")
        ]
        uploaded = docs.add_files(files, metadata={"section": "guides"})
        texts = docs.add_texts(
            [
                {
                    "title": "Payout note",
                    "text": "Payouts arrive after two business days.",
                    "external_id": "payout-note",
                }
            ]
        )
        assert len(uploaded.created) == 2
        assert [d.external_id for d in texts.created] == ["payout-note"]
        version = docs.wait_until_indexed()
        assert version.index.status == "ready"
        assert version.index.progress.ready == 3

        result = docs.query("How do I verify a webhook signature?", top_k=3)
        assert result.hits[0].external_id == "webhooks"
        assert result.hits[0].metadata == {"section": "guides"}
        answer = docs.answer("What is the live mode rate limit?")
        assert answer.citations
        assert "100" in answer.answer

        vector = docs.create_pipeline(
            "Vector only", {**HASH_PIPELINE, "retrieval": {"mode": "vector"}}
        )
        assert vector.index.shared_with == [1]
        assert [p.version for p in docs.pipelines()] == [2, 1]

        dataset = rk.evals.create_dataset(
            "CI smoke",
            "docs",
            [
                {
                    "question": "How old can a webhook event be before I reject it?",
                    "expected_sources": [
                        {"document": "webhooks", "evidence": "more than five minutes old"}
                    ],
                    "expected_answer": "Five minutes.",
                },
                {
                    "question": "What is the live mode rate limit?",
                    "expected_sources": [
                        {
                            "document": "rate-limits",
                            "evidence": "Mode: Live mode; Requests per second: 100",
                        }
                    ],
                    "expected_answer": "100 requests per second.",
                },
            ],
            slug="ci-smoke",
            gate={"min": {"hit_rate": 0.5}},
        )
        assert dataset.item_count == 2
        first = rk.evals.run("ci-smoke")
        second = rk.evals.run("ci-smoke", pipeline_version=2)
        assert first.status == second.status == "completed"
        assert len(rk.evals.results(first.id)) == 2
        comparison = rk.evals.compare([first.id, second.id])
        assert {"key": "retrieval.mode", "values": ["hybrid", "vector"]} in comparison.config_diff
        rk.evals.set_baseline(first.id)
        assert rk.evals.gate(second.id, max_drop=1.0).passed

    runner = CliRunner()
    env = {"RAGKIT_URL": server, "RAGKIT_API_KEY": key, "RAGKIT_PROJECT": project}
    report = tmp_path / "gate.md"
    passed = runner.invoke(
        cli, ["eval", "gate", "ci-smoke", "--min", "hit_rate=0.5", "--report", str(report)], env=env
    )
    assert passed.exit_code == 0, passed.output
    assert "RAGKit evaluation gate: PASSED" in report.read_text()
    failed = runner.invoke(cli, ["eval", "gate", "ci-smoke", "--min", "hit_rate=1.5"], env=env)
    assert failed.exit_code == 1, failed.output
    queried = runner.invoke(cli, ["query", "docs", "webhook signature", "--top-k", "2"], env=env)
    assert queried.exit_code == 0
    assert "webhooks" in queried.output
