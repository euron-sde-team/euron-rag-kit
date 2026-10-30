from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ragkit.cli import app
from ragkit.gate import parse_thresholds
from tests.conftest import PROJECT, run_body

runner = CliRunner()
GATE = {
    "passed": True,
    "run_id": "run-1",
    "run_status": "completed",
    "baseline_run_id": "run-0",
    "checks": [
        {
            "metric": "hit_rate",
            "kind": "min",
            "threshold": 0.9,
            "value": 0.95,
            "baseline": None,
            "passed": True,
            "message": "ok",
        },
        {
            "metric": "mrr",
            "kind": "max_drop",
            "threshold": 0.03,
            "value": 0.81,
            "baseline": 0.8,
            "passed": True,
            "message": "ok",
        },
    ],
}


def mock_run(api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, **run: object) -> None:
    monkeypatch.setattr("ragkit.client.time.sleep", lambda _: None)
    api.post(f"{PROJECT}/eval-runs").mock(
        return_value=httpx.Response(201, json=run_body(status="queued"))
    )
    api.get(f"{PROJECT}/eval-runs/run-1").mock(
        return_value=httpx.Response(200, json=run_body(**run))
    )


def test_thresholds_parse_and_reject_bad_pairs() -> None:
    assert parse_thresholds(["hit_rate=0.85", "mrr=0.6"]) == {"hit_rate": 0.85, "mrr": 0.6}
    with pytest.raises(ValueError, match="metric=value"):
        parse_thresholds(["hit_rate"])
    with pytest.raises(ValueError, match="not a number"):
        parse_thresholds(["hit_rate=high"])


def test_gate_passes_and_writes_a_markdown_report(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mock_run(api, monkeypatch)
    gate = api.post(f"{PROJECT}/eval-runs/run-1/gate").mock(
        return_value=httpx.Response(200, json=GATE)
    )
    report = tmp_path / "gate.md"
    result = runner.invoke(
        app,
        [
            "eval",
            "gate",
            "smoke",
            "--min",
            "hit_rate=0.9",
            "--max-drop",
            "0.03",
            "--report",
            str(report),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "RAGKit evaluation gate: PASSED" in report.read_text()
    assert gate.calls.last.request.content == b'{"min":{"hit_rate":0.9},"max_drop":0.03}'


def test_gate_fails_with_exit_code_1_on_regression(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_run(api, monkeypatch)
    failed = {
        **GATE,
        "passed": False,
        "checks": [{**GATE["checks"][1], "passed": False, "message": "-0.050 vs baseline"}],
    }  # type: ignore[index]
    api.post(f"{PROJECT}/eval-runs/run-1/gate").mock(return_value=httpx.Response(200, json=failed))
    result = runner.invoke(app, ["eval", "gate", "smoke", "--format", "json"])
    assert result.exit_code == 1
    assert '"status": "failed"' in result.output


def test_gate_reports_a_failed_run_with_exit_code_2(
    api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_run(
        api, monkeypatch, status="failed", error="The collection or pipeline version was deleted."
    )
    result = runner.invoke(app, ["eval", "gate", "smoke"])
    assert result.exit_code == 2
    assert "did not complete" in result.output


def test_unreachable_api_exits_with_2(api: respx.MockRouter) -> None:
    api.post(f"{PROJECT}/collections/developer-docs/query").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = runner.invoke(app, ["query", "developer-docs", "anything"])
    assert result.exit_code == 2
    assert "Cannot reach RAGKit" in result.output
