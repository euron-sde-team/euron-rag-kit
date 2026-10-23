"""Side-by-side comparison of evaluation runs.

The first run is the reference: every other run's metrics are reported with deltas against
it, configuration snapshots are flattened and diffed, and, when the runs share a dataset,
each question is classified as improved, regressed or unchanged by the mean of its ndcg,
context recall and answer correctness (a change over 0.05 counts).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ragkit_server.evaluation.metrics import METRICS

CHANGE_THRESHOLD = 0.05
COMPOSITE = ("ndcg", "context_recall", "answer_correctness")


@dataclass(frozen=True, slots=True)
class RunView:
    id: str
    label: str
    dataset_id: str
    means: Mapping[str, float]
    config: Mapping[str, Any]
    latency_p50: float = 0.0


@dataclass(frozen=True, slots=True)
class ItemView:
    key: str
    question: str
    metrics: Mapping[str, float | None]
    tags: Sequence[str] = field(default_factory=tuple)
    top_documents: Sequence[str] = field(default_factory=tuple)


def flatten(config: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in config.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            flat.update(flatten(value, path))
        else:
            flat[path] = value
    return flat


def config_diff(configs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    flats = [flatten(config) for config in configs]
    keys = sorted({key for flat in flats for key in flat})
    return [
        {"key": key, "values": [flat.get(key) for flat in flats]}
        for key in keys
        if len({repr(flat.get(key)) for flat in flats}) > 1
    ]


def composite(values: Mapping[str, float | None]) -> float | None:
    present = [v for name in COMPOSITE if (v := values.get(name)) is not None]
    return sum(present) / len(present) if present else None


def compare(
    runs: Sequence[RunView], items: Mapping[str, Sequence[ItemView]] | None = None
) -> dict[str, Any]:
    reference = runs[0]
    metric_rows = []
    for metric in METRICS:
        values = [run.means.get(metric) for run in runs]
        if all(value is None for value in values):
            continue
        base = values[0]
        metric_rows.append(
            {
                "metric": metric,
                "values": values,
                "deltas": [
                    None if value is None or base is None else round(value - base, 4)
                    for value in values
                ],
            }
        )
    same_dataset = len({run.dataset_id for run in runs}) == 1
    questions: list[dict[str, Any]] = []
    summary = {"improved": 0, "regressed": 0, "unchanged": 0}
    if same_dataset and items is not None:
        by_run = [{item.key: item for item in items.get(run.id, ())} for run in runs]
        for key, first in by_run[0].items():
            entries = [mapping.get(key) for mapping in by_run]
            scores = [composite(entry.metrics) if entry else None for entry in entries]
            base = scores[0]
            statuses = []
            for score in scores[1:]:
                if score is None or base is None:
                    statuses.append("missing")
                elif score - base > CHANGE_THRESHOLD:
                    statuses.append("improved")
                elif base - score > CHANGE_THRESHOLD:
                    statuses.append("regressed")
                else:
                    statuses.append("unchanged")
            if statuses and statuses[-1] in summary:
                summary[statuses[-1]] += 1
            questions.append(
                {
                    "key": key,
                    "question": first.question,
                    "tags": list(first.tags),
                    "scores": scores,
                    "statuses": statuses,
                    "metrics": [dict(entry.metrics) if entry else None for entry in entries],
                    "top_documents": [
                        list(entry.top_documents) if entry else [] for entry in entries
                    ],
                }
            )
        questions.sort(key=lambda q: _swing(q["scores"]))
    return {
        "reference_run": reference.id,
        "same_dataset": same_dataset,
        "metrics": metric_rows,
        "config_diff": config_diff([run.config for run in runs]),
        "questions": questions,
        "summary": summary,
    }


def _swing(scores: Sequence[float | None]) -> tuple[int, float]:
    """Regressions first (worst first), then improvements (best first), then the rest."""
    if len(scores) < 2 or scores[0] is None or scores[-1] is None:
        return (2, 0.0)
    change = scores[-1] - scores[0]
    return (0, change) if change < 0 else (1, -change)
