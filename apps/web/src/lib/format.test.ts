import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatCompact,
  formatDuration,
  formatPercent,
  formatRelative,
  initials,
} from "@/lib/format";

describe("formatters", () => {
  it("formats sizes, ratios and durations", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(50 * 1024 * 1024)).toBe("50 MB");
    expect(formatPercent(0.7512)).toBe("75%");
    expect(formatPercent(0.7512, 1)).toBe("75.1%");
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(1380)).toBe("1.4 s");
    expect(formatCompact(4754)).toBe("4,754");
    expect(formatCompact(125_000)).toBe("125K");
  });

  it("formats relative times", () => {
    const now = new Date("2026-10-23T12:00:00Z");
    expect(formatRelative("2026-10-23T11:59:30Z", now)).toBe("just now");
    expect(formatRelative("2026-10-23T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelative("2026-10-20T12:00:00Z", now)).toBe("3 days ago");
  });

  it("builds initials", () => {
    expect(initials("Ava Martin")).toBe("AM");
    expect(initials("leo")).toBe("L");
    expect(initials("  ")).toBe("?");
  });
});
