import pytest

from ragkit_server.core.errors import UnprocessableError
from ragkit_server.evaluation.aggregate import ResultRow, aggregate, percentile
from ragkit_server.evaluation.compare import ItemView, RunView, compare, config_diff, flatten
from ragkit_server.evaluation.gate import expand_drop, run_gate


def test_aggregate_means_counts_latency_and_tags() -> None:
    rows = [
        ResultRow({"hit_rate": 1.0, "mrr": 1.0, "answer_correctness": 0.5}, ("keyword",), 100),
        ResultRow({"hit_rate": 0.0, "mrr": 0.0, "answer_correctness": None}, ("semantic",), 300),
        ResultRow({"hit_rate": 1.0, "mrr": 0.5}, ("keyword", "numeric"), 200),
        ResultRow({}, (), 0, failed=True),
    ]
    result = aggregate(rows)
    assert result["means"]["hit_rate"] == pytest.approx(0.6667)
    assert result["counts"] == {"hit_rate": 3, "mrr": 3, "answer_correctness": 1}
    assert result["failed"] == 1
    assert result["questions"] == 4
    assert result["latency_ms"]["p50"] == 200.0
    assert result["by_tag"]["keyword"] == {
        "questions": 2,
        "means": {"hit_rate": 1.0, "mrr": 0.75, "answer_correctness": 0.5},
    }


def test_percentile_interpolates() -> None:
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([5], 0.95) == 5
    assert percentile([], 0.5) == 0.0


def test_gate_floors_and_drops() -> None:
    candidate = {"hit_rate": 0.86, "mrr": 0.70, "ndcg": 0.74}
    baseline = {"hit_rate": 0.88, "mrr": 0.75, "ndcg": 0.74}
    passed, checks = run_gate(
        candidate, baseline, minimums={"hit_rate": 0.85}, max_drop={"hit_rate": 0.03, "mrr": 0.03}
    )
    assert not passed
    by_kind = {(c.metric, c.kind): c for c in checks}
    assert by_kind[("hit_rate", "min")].passed
    assert by_kind[("hit_rate", "max_drop")].passed
    assert not by_kind[("mrr", "max_drop")].passed
    assert "beyond" in by_kind[("mrr", "max_drop")].message


def test_gate_fails_unmeasured_metrics_and_missing_baselines() -> None:
    passed, checks = run_gate(
        {"hit_rate": 1.0}, None, minimums={"faithfulness": 0.9}, max_drop={"hit_rate": 0.1}
    )
    assert not passed
    assert [c.message for c in checks] == ["not measured", "no baseline run"]
    with pytest.raises(UnprocessableError):
        run_gate({}, None, minimums={"accuracy": 0.9}, max_drop={})


def test_a_single_drop_limit_covers_every_measured_metric() -> None:
    assert expand_drop(0.02, {"hit_rate": 1.0, "mrr": 1.0}) == {"hit_rate": 0.02, "mrr": 0.02}
    assert expand_drop({"mrr": 0.1}, {}) == {"mrr": 0.1}
    assert expand_drop(None, {"mrr": 1.0}) == {}


def test_configuration_diffs_are_flat_and_minimal() -> None:
    a = {"chunking": {"strategy": "fixed", "chunk_tokens": 200}, "retrieval": {"mode": "vector"}}
    b = {
        "chunking": {"strategy": "recursive", "chunk_tokens": 200},
        "retrieval": {"mode": "hybrid"},
    }
    assert flatten(a)["chunking.chunk_tokens"] == 200
    assert config_diff([a, b]) == [
        {"key": "chunking.strategy", "values": ["fixed", "recursive"]},
        {"key": "retrieval.mode", "values": ["vector", "hybrid"]},
    ]


def test_compare_reports_deltas_and_classifies_questions() -> None:
    runs = [
        RunView(
            "r1",
            "baseline",
            "d1",
            {"hit_rate": 0.5, "ndcg": 0.4},
            {"retrieval": {"mode": "vector"}},
        ),
        RunView(
            "r2", "hybrid", "d1", {"hit_rate": 0.75, "ndcg": 0.6}, {"retrieval": {"mode": "hybrid"}}
        ),
    ]
    items = {
        "r1": [
            ItemView("q1", "Refund window?", {"ndcg": 0.0, "context_recall": 0.0}),
            ItemView("q2", "Rate limit?", {"ndcg": 1.0, "context_recall": 1.0}),
            ItemView("q3", "Payout time?", {"ndcg": 0.5, "context_recall": 1.0}),
        ],
        "r2": [
            ItemView("q1", "Refund window?", {"ndcg": 1.0, "context_recall": 1.0}),
            ItemView("q2", "Rate limit?", {"ndcg": 0.5, "context_recall": 1.0}),
            ItemView("q3", "Payout time?", {"ndcg": 0.52, "context_recall": 1.0}),
        ],
    }
    result = compare(runs, items)
    hit_rate = next(row for row in result["metrics"] if row["metric"] == "hit_rate")
    assert hit_rate["deltas"] == [0.0, 0.25]
    assert result["summary"] == {"improved": 1, "regressed": 1, "unchanged": 1}
    assert result["questions"][0]["key"] == "q2"  # regressions first
    assert result["config_diff"] == [{"key": "retrieval.mode", "values": ["vector", "hybrid"]}]


def test_runs_of_different_datasets_compare_only_aggregates() -> None:
    runs = [RunView("a", "a", "d1", {"mrr": 0.5}, {}), RunView("b", "b", "d2", {"mrr": 0.6}, {})]
    result = compare(runs, {"a": [], "b": []})
    assert not result["same_dataset"]
    assert result["questions"] == []
