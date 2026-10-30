"""Thresholds in, a CI-friendly verdict out: parsing `metric=value` options and reports."""

from __future__ import annotations

import json

from ragkit.models import GateResult, Run

EXIT_PASSED = 0
EXIT_REGRESSED = 1
EXIT_ERROR = 2


def parse_thresholds(pairs: list[str]) -> dict[str, float]:
    """["hit_rate=0.85", "mrr=0.6"] -> {"hit_rate": 0.85, "mrr": 0.6}."""
    thresholds: dict[str, float] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"expected metric=value, got {pair!r}")
        try:
            thresholds[name.strip()] = float(value)
        except ValueError as exc:
            raise ValueError(f"{name.strip()}: {value!r} is not a number") from exc
    return thresholds


def exit_code(run: Run, verdict: GateResult | None) -> int:
    if run.status != "completed" or verdict is None:
        return EXIT_ERROR
    return EXIT_PASSED if verdict.passed else EXIT_REGRESSED


def _number(value: float | None) -> str:
    return "" if value is None else f"{value:.3f}"


def markdown_report(run: Run, verdict: GateResult | None) -> str:
    """A report to post as a pull request comment or a CI job summary."""
    status = {EXIT_PASSED: "PASSED", EXIT_REGRESSED: "FAILED"}.get(exit_code(run, verdict), "ERROR")
    lines = [
        f"## RAGKit evaluation gate: {status}",
        "",
        f"Run **{run.label}** (`{run.id}`) on dataset `{run.dataset.get('slug', '')}`, "
        f"pipeline version {run.pipeline_version}, k = {run.k}: {run.status}.",
        "",
    ]
    if run.status != "completed":
        lines.append(f"The run did not complete: {run.error or run.status}.")
        return "\n".join(lines) + "\n"
    if verdict is not None and verdict.checks:
        lines += [
            "| Metric | Check | Threshold | Value | Baseline | Result |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for check in verdict.checks:
            threshold = (
                f">= {check.threshold:.3f}"
                if check.kind == "min"
                else f"drop <= {check.threshold:.3f}"
            )
            lines.append(
                f"| {check.metric} | {check.kind} | {threshold} | {_number(check.value)} | "
                f"{_number(check.baseline)} | {'pass' if check.passed else 'FAIL'} |"
            )
        lines.append("")
    means = run.means
    if means:
        lines += ["| Metric | Value |", "| --- | --- |"]
        lines += [f"| {name} | {value:.3f} |" for name, value in sorted(means.items())]
    return "\n".join(lines) + "\n"


def json_report(run: Run, verdict: GateResult | None) -> str:
    return json.dumps(
        {
            "status": {EXIT_PASSED: "passed", EXIT_REGRESSED: "failed"}.get(
                exit_code(run, verdict), "error"
            ),
            "run": {
                "id": run.id,
                "label": run.label,
                "status": run.status,
                "pipeline_version": run.pipeline_version,
                "k": run.k,
                "means": run.means,
            },
            "checks": [check.model_dump() for check in verdict.checks] if verdict else [],
        },
        indent=2,
    )
