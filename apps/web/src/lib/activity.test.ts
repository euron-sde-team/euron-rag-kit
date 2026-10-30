import { describe, expect, it } from "vitest";

import { describeEvent } from "@/lib/activity";
import type { AuditEvent } from "@/lib/types";

const event = (
  action: string,
  details: Record<string, unknown>,
  actor: string | null = "Priya Raman",
): AuditEvent => ({
  id: "1",
  action,
  target_type: "x",
  target_id: null,
  details,
  actor,
  created_at: "2026-10-30T10:00:00Z",
});

describe("describeEvent", () => {
  it("names the version and collection of pipeline changes", () => {
    expect(
      describeEvent(event("pipeline.activated", { collection: "developer-docs", version: 2 })),
    ).toEqual({
      actor: "Priya Raman",
      phrase: "activated v2 of developer-docs",
    });
    expect(
      describeEvent(event("pipeline.created", { collection: "docs", version: 3, index: "shared" }))
        .phrase,
    ).toBe("created v3 of docs (reusing an index)");
  });

  it("credits API keys when there is no person", () => {
    expect(describeEvent(event("document.added", { external_id: "webhooks" }, null))).toEqual({
      actor: "An API key",
      phrase: "added webhooks",
    });
  });

  it("describes dataset imports that replace questions", () => {
    expect(describeEvent(event("dataset.items_imported", { items: 4, replace: true })).phrase).toBe(
      "replaced the questions with 4 questions",
    );
  });

  it("falls back to a readable action name", () => {
    expect(describeEvent(event("index.rebuilt", {})).phrase).toBe("index rebuilt");
  });
});
