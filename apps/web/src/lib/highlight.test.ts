import { describe, expect, it } from "vitest";

import { highlight, queryTerms } from "@/lib/highlight";

describe("highlight", () => {
  it("keeps the meaningful words of a query", () => {
    expect(queryTerms("How do I verify the webhook signature?")).toEqual([
      "verify",
      "webhook",
      "signature",
    ]);
  });

  it("marks word starts, case-insensitively, as plain segments", () => {
    const segments = highlight("Refunds and refunded charges", ["refund"]);
    expect(segments.filter((s) => s.match).map((s) => s.text)).toEqual(["Refunds", "refunded"]);
    expect(segments.map((s) => s.text).join("")).toBe("Refunds and refunded charges");
  });

  it("treats regex characters in terms literally", () => {
    expect(highlight("a.b and axb", ["a.b"]).filter((s) => s.match)).toEqual([
      { text: "a.b", match: true },
    ]);
  });

  it("returns the text unchanged without terms", () => {
    expect(highlight("<b>tag</b>", [])).toEqual([{ text: "<b>tag</b>", match: false }]);
  });
});
