import { describe, expect, it } from "vitest";

import {
  DEFAULT_CONFIG,
  PRESETS,
  configGroups,
  describeConfig,
  indexKey,
  sharedIndexWith,
} from "@/lib/pipeline";
import type { PipelineVersion } from "@/lib/types";

const version = (n: number, config = DEFAULT_CONFIG): PipelineVersion =>
  ({ version: n, config }) as PipelineVersion;

describe("pipeline helpers", () => {
  it("describes a configuration in pipeline order", () => {
    expect(describeConfig(PRESETS[0]!.config)).toEqual([
      "Recursive 256 tok / 32",
      "bge-small-en-v1.5",
      "Hybrid RRF",
      "Cross-encoder",
    ]);
  });

  it("ignores retrieval settings and unused knobs when keying an index", () => {
    const retrievalOnly = {
      ...DEFAULT_CONFIG,
      retrieval: { ...DEFAULT_CONFIG.retrieval, mode: "vector" as const },
    };
    expect(indexKey(retrievalOnly)).toBe(indexKey(DEFAULT_CONFIG));
    const unused = {
      ...DEFAULT_CONFIG,
      chunking: { ...DEFAULT_CONFIG.chunking, window_sentences: 7 },
    };
    expect(indexKey(unused)).toBe(indexKey(DEFAULT_CONFIG));
    const rechunked = {
      ...DEFAULT_CONFIG,
      chunking: { ...DEFAULT_CONFIG.chunking, chunk_tokens: 128 },
    };
    expect(indexKey(rechunked)).not.toBe(indexKey(DEFAULT_CONFIG));
  });

  it("finds the version whose index a draft would reuse", () => {
    const versions = [version(2, PRESETS[1]!.config), version(1)];
    expect(sharedIndexWith(DEFAULT_CONFIG, versions)?.version).toBe(1);
    expect(sharedIndexWith(PRESETS[2]!.config, versions)).toBeNull();
  });

  it("lists only the knobs a configuration uses", () => {
    const groups = configGroups(DEFAULT_CONFIG);
    expect(groups.map((g) => g.id)).toEqual([
      "cleaning",
      "chunking",
      "embedding",
      "retrieval",
      "answer",
    ]);
    const chunking = groups.find((g) => g.id === "chunking")!.rows.map(([label]) => label);
    expect(chunking).toEqual(["Strategy", "Chunk tokens", "Overlap tokens"]);
    const retrieval = Object.fromEntries(groups.find((g) => g.id === "retrieval")!.rows);
    expect(retrieval.Fusion).toBe("RRF (k 60)");
    expect(retrieval["Rerank candidates"]).toBeUndefined();

    const windows = configGroups(PRESETS[2]!.config);
    const windowRows = windows.find((g) => g.id === "chunking")!.rows.map(([label]) => label);
    expect(windowRows).toContain("Window sentences");
    expect(windowRows).not.toContain("Overlap tokens");
    expect(
      Object.fromEntries(windows.find((g) => g.id === "retrieval")!.rows)["Rerank candidates"],
    ).toBe("20");
  });
});
