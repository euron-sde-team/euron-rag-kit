/** Retrieval stages as the playground draws them: which ran, how scores compare, how long. */

import type { Hit, QueryResult, Stage } from "@/lib/types";

export type StageInfo = { id: Stage; label: string; color: string };

export const STAGE_INFO: Record<Stage, StageInfo> = {
  vector: { id: "vector", label: "Vector", color: "var(--stage-vector)" },
  keyword: { id: "keyword", label: "Keyword", color: "var(--stage-keyword)" },
  fused: { id: "fused", label: "Fused", color: "var(--stage-fusion)" },
  rerank: { id: "rerank", label: "Rerank", color: "var(--stage-rerank)" },
};

/** The stages that ran for a result, in pipeline order. */
export function activeStages(result: Pick<QueryResult, "mode" | "rerank">): Stage[] {
  const stages: Stage[] = [];
  if (result.mode !== "keyword") stages.push("vector");
  if (result.mode !== "vector") stages.push("keyword");
  if (result.mode === "hybrid") stages.push("fused");
  if (result.rerank.kind !== "none") stages.push("rerank");
  return stages;
}

/** The best score per stage among the hits, to scale each stage's bars on its own range. */
export function stageMaxima(hits: Hit[]): Record<Stage, number> {
  const maxima: Record<Stage, number> = { vector: 0, keyword: 0, fused: 0, rerank: 0 };
  for (const hit of hits) {
    for (const stage of Object.keys(maxima) as Stage[]) {
      const score = hit.scores[stage];
      if (score !== null && score > maxima[stage]) maxima[stage] = score;
    }
  }
  return maxima;
}

/** Places a hit gained (positive) or lost in reranking, or null when nothing reranked it. */
export function rerankMovement(hit: Hit): number | null {
  if (hit.ranks.rerank === null || hit.ranks.fused === null) return null;
  return hit.ranks.fused - hit.rank;
}

const TIMED: { key: string; label: string; color: string }[] = [
  { key: "embed", label: "Embed query", color: "var(--stage-embed)" },
  { key: "vector", label: "Vector search", color: "var(--stage-vector)" },
  { key: "keyword", label: "Keyword search", color: "var(--stage-keyword)" },
  { key: "fusion", label: "Fusion", color: "var(--stage-fusion)" },
  { key: "rerank", label: "Rerank", color: "var(--stage-rerank)" },
];

export type TimingSegment = {
  key: string;
  label: string;
  color: string;
  ms: number;
  share: number;
};

/** Stage timings as shares of their sum, in pipeline order, skipping stages that did not run. */
export function timingSegments(timings: Record<string, number>): TimingSegment[] {
  const present = TIMED.filter((stage) => timings[stage.key] !== undefined);
  const sum = present.reduce((total, stage) => total + (timings[stage.key] ?? 0), 0);
  return present.map((stage) => {
    const ms = timings[stage.key] ?? 0;
    return { ...stage, ms, share: sum > 0 ? ms / sum : 0 };
  });
}
