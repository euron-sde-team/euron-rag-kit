"""The regression gate behind `ragkit eval gate`.

Two kinds of check, each on one metric of the candidate run:

- a floor: `value >= min`,
- a drop limit against a baseline run: `value >= baseline - max_drop`.

A metric the candidate did not measure fails its check, so a misconfigured run (no answers,
no expected sources) cannot pass a gate by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from ragkit_server.core.errors import UnprocessableError
from ragkit_server.evaluation.metrics import METRICS

EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class GateCheck:
    metric: str
    kind: str
    threshold: float
    value: float | None
    baseline: float | None
    passed: bool
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _known(metric: str) -> str:
    if metric not in METRICS:
        raise UnprocessableError(
            f"Unknown metric '{metric}'. Gate on one of {', '.join(METRICS)}.",
            code="validation_failed",
        )
    return metric


def run_gate(
    candidate: Mapping[str, float],
    baseline: Mapping[str, float] | None,
    *,
    minimums: Mapping[str, float],
    max_drop: Mapping[str, float],
) -> tuple[bool, list[GateCheck]]:
    checks: list[GateCheck] = []
    for metric, floor in minimums.items():
        value = candidate.get(_known(metric))
        if value is None:
            checks.append(GateCheck(metric, "min", floor, None, None, False, "not measured"))
            continue
        passed = value + EPSILON >= floor
        verdict = "meets" if passed else "is below"
        checks.append(
            GateCheck(
                metric, "min", floor, value, None, passed, f"{value:.3f} {verdict} {floor:.3f}"
            )
        )
    for metric, drop in max_drop.items():
        value = candidate.get(_known(metric))
        reference = baseline.get(metric) if baseline is not None else None
        if baseline is None:
            checks.append(
                GateCheck(metric, "max_drop", drop, value, None, False, "no baseline run")
            )
            continue
        if value is None or reference is None:
            checks.append(
                GateCheck(metric, "max_drop", drop, value, reference, False, "not measured")
            )
            continue
        change = value - reference
        passed = change + EPSILON >= -drop
        message = f"{change:+.3f} vs baseline ({'within' if passed else 'beyond'} -{drop:.3f})"
        checks.append(GateCheck(metric, "max_drop", drop, value, reference, passed, message))
    return all(check.passed for check in checks), checks


def expand_drop(
    max_drop: float | Mapping[str, float] | None, metrics: Mapping[str, float]
) -> dict[str, float]:
    """A single drop limit applies to every metric the candidate measured."""
    if max_drop is None:
        return {}
    if isinstance(max_drop, Mapping):
        return dict(max_drop)
    return {metric: float(max_drop) for metric in METRICS if metric in metrics}
