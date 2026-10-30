import { describe, expect, it } from "vitest";

import { compareOrder, deltaAgainst, runTick, trendPoints } from "@/lib/runs";
import type { Run } from "@/lib/types";

function run(
  id: string,
  created: string,
  means: Record<string, number>,
  extra: Partial<Run> = {},
): Run {
  return {
    id,
    label: `run ${id}`,
    status: "completed",
    dataset: { id: "d", slug: "golden", name: "Golden" },
    collection: { id: "c", slug: "docs", name: "Docs" },
    pipeline_version: 2,
    k: 5,
    grader: "deterministic",
    config: {} as Run["config"],
    total_items: 10,
    completed_items: 10,
    metrics: { means },
    error: null,
    is_baseline: false,
    created_at: created,
    started_at: created,
    finished_at: created,
    duration_ms: 1000,
    ...extra,
  };
}

describe("runs", () => {
  const older = run("a", "2026-10-20T10:00:00Z", { mrr: 0.8 });
  const newer = run("b", "2026-10-28T10:00:00Z", { mrr: 0.9 }, { pipeline_version: 3 });
  const pending = run("c", "2026-10-29T10:00:00Z", {}, { status: "running" });

  it("names a run by version and day", () => {
    expect(runTick(newer)).toBe("v3, Oct 28");
  });

  it("charts completed runs oldest first", () => {
    const points = trendPoints([newer, pending, older], ["mrr", "ndcg"]);
    expect(points.map((p) => p.id)).toEqual(["a", "b"]);
    expect(points[1]).toMatchObject({ mrr: 0.9, ndcg: null, label: "run b" });
  });

  it("puts a selected baseline first, otherwise the oldest run", () => {
    expect(compareOrder([newer, older])).toEqual(["a", "b"]);
    const baseline = { ...newer, is_baseline: true };
    expect(compareOrder([older, baseline])).toEqual(["b", "a"]);
  });

  it("computes deltas only against a different run that measured the metric", () => {
    expect(deltaAgainst(newer, older, "mrr")).toBeCloseTo(0.1);
    expect(deltaAgainst(newer, newer, "mrr")).toBeNull();
    expect(deltaAgainst(newer, older, "ndcg")).toBeNull();
    expect(deltaAgainst(newer, undefined, "mrr")).toBeNull();
  });
});
