/** Evaluation runs as the dashboard orders, names and charts them. */

import type { Run } from "@/lib/types";

const SHORT_DATE = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

export function shortDate(iso: string): string {
  return SHORT_DATE.format(new Date(iso));
}

/** A compact name for legends and axes: version and day, e.g. "v2, Oct 28". */
export function runTick(run: Pick<Run, "pipeline_version" | "created_at">): string {
  return `v${run.pipeline_version}, ${shortDate(run.created_at)}`;
}

export type TrendPoint = { name: string; label: string; id: string } & Record<
  string,
  number | string | null
>;

/** Completed runs, oldest first, as chart points carrying the chosen metric means. */
export function trendPoints(runs: Run[], metrics: string[]): TrendPoint[] {
  return runs
    .filter((run) => run.status === "completed")
    .toSorted((a, b) => a.created_at.localeCompare(b.created_at))
    .map((run) => {
      const point: TrendPoint = { name: runTick(run), label: run.label, id: run.id };
      for (const metric of metrics) point[metric] = run.metrics.means?.[metric] ?? null;
      return point;
    });
}

/**
 * Comparison order: the reference first. A selected baseline is the natural reference;
 * otherwise the oldest run is, so deltas read as "what changed since".
 */
export function compareOrder(selected: Run[]): string[] {
  const sorted = selected.toSorted((a, b) => a.created_at.localeCompare(b.created_at));
  const baseline = sorted.find((run) => run.is_baseline);
  return baseline
    ? [baseline.id, ...sorted.filter((r) => r !== baseline).map((r) => r.id)]
    : sorted.map((r) => r.id);
}

/** Metric delta of a run against a reference, when both measured it. */
export function deltaAgainst(run: Run, reference: Run | undefined, metric: string): number | null {
  if (!reference || reference.id === run.id) return null;
  const value = run.metrics.means?.[metric];
  const base = reference.metrics.means?.[metric];
  return value === undefined || base === undefined ? null : value - base;
}
