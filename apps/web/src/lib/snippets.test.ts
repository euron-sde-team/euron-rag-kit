import { describe, expect, it } from "vitest";

import { snippets } from "@/lib/snippets";

describe("snippets", () => {
  const all = snippets({
    apiUrl: "http://localhost:8160",
    project: "acme-payments",
    collection: "developer-docs",
    dataset: "support-golden",
    key: "rgk_abc_secret",
  });

  it("puts the key, project and collection into every example", () => {
    for (const text of Object.values(all)) {
      expect(text).toContain("rgk_abc_secret");
      expect(text).toContain("acme-payments");
    }
    expect(all.curl).toContain("/api/v1/projects/acme-payments/collections/developer-docs/query");
    expect(all.python).toContain('rk.collection("developer-docs")');
  });

  it("gates CI on the dataset", () => {
    expect(all.cli).toContain("ragkit eval gate support-golden");
  });
});
