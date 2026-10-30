import { describe, expect, it } from "vitest";

import { splitAnswer } from "@/lib/citations";

describe("splitAnswer", () => {
  it("turns markers into citation parts and keeps the text around them", () => {
    expect(
      splitAnswer("Live mode allows 100 requests per second [1]. Test mode allows 25 [2]."),
    ).toEqual([
      { kind: "text", text: "Live mode allows 100 requests per second" },
      { kind: "cite", n: 1 },
      { kind: "text", text: ". Test mode allows 25" },
      { kind: "cite", n: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("handles adjacent markers and answers without any", () => {
    expect(splitAnswer("Yes [1] [3]")).toEqual([
      { kind: "text", text: "Yes" },
      { kind: "cite", n: 1 },
      { kind: "cite", n: 3 },
    ]);
    expect(splitAnswer("No sources.")).toEqual([{ kind: "text", text: "No sources." }]);
  });
});
