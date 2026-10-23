"""A run's aggregate metrics from its per-question results.

Each metric is averaged over the questions it applies to: retrieval metrics need expected
sources, correctness needs a reference answer, answer metrics need a generated answer.
The number of questions behind each mean is kept next to it, so "0.92 over 3 questions" is
never mistaken for "0.92 over 300".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ragkit_server.evaluation.metrics import METRICS


@dataclass(frozen=True, slots=True)
class ResultRow:
    metrics: Mapping[str, float | None]
    tags: Sequence[str] = field(default_factory=tuple)
    latency_ms: int = 0
    failed: bool = False


def percentile(values: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks (the numpy default)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _means(rows: Sequence[ResultRow]) -> tuple[dict[str, float], dict[str, int]]:
    means: dict[str, float] = {}
    counts: dict[str, int] = {}
    for metric in METRICS:
        values = [v for row in rows if (v := row.metrics.get(metric)) is not None]
        if values:
            means[metric] = round(sum(values) / len(values), 4)
            counts[metric] = len(values)
    return means, counts


def aggregate(rows: Sequence[ResultRow]) -> dict[str, Any]:
    scored = [row for row in rows if not row.failed]
    means, counts = _means(scored)
    latencies = [float(row.latency_ms) for row in scored]
    by_tag: dict[str, dict[str, Any]] = {}
    for tag in sorted({tag for row in scored for tag in row.tags}):
        tagged = [row for row in scored if tag in row.tags]
        tag_means, _ = _means(tagged)
        by_tag[tag] = {"questions": len(tagged), "means": tag_means}
    return {
        "means": means,
        "counts": counts,
        "questions": len(rows),
        "failed": len(rows) - len(scored),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "mean": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        },
        "by_tag": by_tag,
    }
