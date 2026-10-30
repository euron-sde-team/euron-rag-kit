import { describe, expect, it } from "vitest";

import { pickProject } from "@/lib/project-choice";
import type { ProjectSummary } from "@/lib/types";

const project = (slug: string, collections: number): ProjectSummary => ({
  id: slug,
  slug,
  name: slug,
  role: "owner",
  collection_count: collections,
  member_count: 1,
});

describe("pickProject", () => {
  const projects = [project("alpha", 0), project("acme-payments", 2), project("beta", 1)];

  it("returns the last project when the person still belongs to it", () => {
    expect(pickProject(projects, "beta")).toBe("beta");
  });

  it("falls back to the project with the most collections", () => {
    expect(pickProject(projects, "gone")).toBe("acme-payments");
    expect(pickProject(projects, null)).toBe("acme-payments");
  });

  it("returns null without projects", () => {
    expect(pickProject([], "beta")).toBeNull();
  });
});
