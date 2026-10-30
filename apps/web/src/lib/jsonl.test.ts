import { describe, expect, it } from "vitest";

import { parseJsonl } from "@/lib/jsonl";

describe("parseJsonl", () => {
  it("reads questions with sources, answers and tags", () => {
    const text = [
      '{"question": "What is the live rate limit?", "expected_sources": [{"document": "rate-limits", "evidence": "100 requests per second"}], "expected_answer": "100 per second", "tags": ["limits"]}',
      "",
      '{"question": "Refund window?", "expected_sources": ["refunds-and-disputes"]}',
    ].join("\n");
    const { items, errors } = parseJsonl(text);
    expect(errors).toEqual([]);
    expect(items).toHaveLength(2);
    expect(items[0]?.expected_sources[0]).toEqual({
      document: "rate-limits",
      evidence: "100 requests per second",
    });
    expect(items[1]?.expected_sources).toEqual([{ document: "refunds-and-disputes" }]);
    expect(items[1]?.tags).toEqual([]);
  });

  it("reports bad lines by number and keeps the good ones", () => {
    const text = '{"question": "ok"}\nnot json\n{"answer": "no question"}\n[1, 2]\n';
    const { items, errors } = parseJsonl(text);
    expect(items).toHaveLength(1);
    expect(errors).toEqual([
      "Line 2: not valid JSON",
      "Line 3: needs a question",
      "Line 4: is not a JSON object",
    ]);
  });

  it("rejects malformed expected sources", () => {
    const { errors } = parseJsonl('{"question": "q", "expected_sources": [{"doc": "x"}]}');
    expect(errors).toEqual(["Line 1: each expected source needs a document"]);
  });
});
