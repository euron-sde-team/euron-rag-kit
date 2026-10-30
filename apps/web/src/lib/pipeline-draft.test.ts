import { describe, expect, it } from "vitest";

import { DEFAULT_CONFIG } from "@/lib/pipeline";
import { draftProblems, withStage } from "@/lib/pipeline-draft";

describe("draftProblems", () => {
  it("accepts the defaults", () => {
    expect(draftProblems(DEFAULT_CONFIG)).toEqual([]);
  });

  it("flags overlap above half the chunk and too few candidates", () => {
    const config = withStage(
      withStage(DEFAULT_CONFIG, "chunking", { chunk_tokens: 100, overlap_tokens: 60 }),
      "retrieval",
      { top_k: 10, candidates: 5 },
    );
    expect(draftProblems(config).map((p) => p.path)).toEqual([
      "chunking.overlap_tokens",
      "retrieval.candidates",
    ]);
  });

  it("ignores overlap for sentence windows but checks their own knobs", () => {
    const config = withStage(DEFAULT_CONFIG, "chunking", {
      strategy: "sentence_window",
      overlap_tokens: 999,
      window_sentences: 12,
    });
    expect(draftProblems(config).map((p) => p.path)).toEqual(["chunking.window_sentences"]);
  });

  it("treats an emptied number field as a problem", () => {
    const config = withStage(DEFAULT_CONFIG, "retrieval", { top_k: Number.NaN });
    expect(draftProblems(config).map((p) => p.path)).toContain("retrieval.top_k");
  });

  it("updates one stage without touching the others", () => {
    const next = withStage(DEFAULT_CONFIG, "embedding", { contextual: false });
    expect(next.embedding.contextual).toBe(false);
    expect(next.chunking).toBe(DEFAULT_CONFIG.chunking);
    expect(DEFAULT_CONFIG.embedding.contextual).toBe(true);
  });
});
