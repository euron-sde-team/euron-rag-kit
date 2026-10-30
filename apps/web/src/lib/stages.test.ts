import { describe, expect, it } from "vitest";

import { activeStages, rerankMovement, stageMaxima, timingSegments } from "@/lib/stages";
import type { Hit } from "@/lib/types";

function hit(rank: number, scores: Partial<Hit["scores"]>, ranks: Partial<Hit["ranks"]>): Hit {
  return {
    rank,
    chunk_id: `c${rank}`,
    document_id: "d",
    document_title: "Doc",
    external_id: "doc",
    location: "",
    heading: "",
    text: "",
    context: null,
    metadata: {},
    score: 0,
    scores: { vector: null, keyword: null, fused: null, rerank: null, ...scores },
    ranks: { vector: null, keyword: null, fused: null, rerank: null, ...ranks },
  };
}

describe("stages", () => {
  it("lists the stages each mode runs", () => {
    expect(
      activeStages({ mode: "hybrid", rerank: { kind: "cross-encoder", fallback: false } }),
    ).toEqual(["vector", "keyword", "fused", "rerank"]);
    expect(activeStages({ mode: "vector", rerank: { kind: "none", fallback: false } })).toEqual([
      "vector",
    ]);
    expect(activeStages({ mode: "keyword", rerank: { kind: "lexical", fallback: false } })).toEqual(
      ["keyword", "rerank"],
    );
  });

  it("scales each stage on its own best score", () => {
    const maxima = stageMaxima([
      hit(1, { vector: 0.8, fused: 0.03 }, {}),
      hit(2, { vector: 0.9, keyword: 0.2, fused: 0.02 }, {}),
    ]);
    expect(maxima).toEqual({ vector: 0.9, keyword: 0.2, fused: 0.03, rerank: 0 });
  });

  it("measures how far reranking moved a hit", () => {
    expect(rerankMovement(hit(1, {}, { fused: 4, rerank: 1 }))).toBe(3);
    expect(rerankMovement(hit(3, {}, { fused: 1, rerank: 3 }))).toBe(-2);
    expect(rerankMovement(hit(1, {}, { fused: 1 }))).toBeNull();
  });

  it("splits timings into ordered shares of the stages that ran", () => {
    const segments = timingSegments({ total: 50, rerank: 30, embed: 10, vector: 5, fusion: 5 });
    expect(segments.map((s) => s.key)).toEqual(["embed", "vector", "fusion", "rerank"]);
    expect(segments.map((s) => s.share)).toEqual([0.2, 0.1, 0.1, 0.6]);
    expect(timingSegments({ total: 3 })).toEqual([]);
  });
});
