import { describe, expect, it } from "vitest";

import { deltaTone, formatDelta, formatMetric, metricLabel } from "@/lib/metrics";

describe("metrics", () => {
  it("labels metrics with their cutoff", () => {
    expect(metricLabel("context_recall", 5)).toBe("Recall@5");
    expect(metricLabel("mrr", 5)).toBe("MRR");
    expect(metricLabel("custom")).toBe("custom");
  });

  it("formats values and signed deltas", () => {
    expect(formatMetric(0.96804)).toBe("0.968");
    expect(formatMetric(null)).toBe("n/a");
    expect(formatDelta(0.0244)).toBe("+0.024");
    expect(formatDelta(-0.01)).toBe("-0.010");
    expect(formatDelta(0.0001)).toBe("0.000");
  });

  it("ignores noise when toning deltas", () => {
    expect(deltaTone(0.02)).toBe("up");
    expect(deltaTone(-0.02)).toBe("down");
    expect(deltaTone(0.001)).toBe("flat");
    expect(deltaTone(null)).toBe("flat");
  });
});
