import { describe, expect, it } from "vitest";

import { errorFrom } from "@/lib/api";

describe("errorFrom", () => {
  it("reads the server's error envelope", () => {
    const error = errorFrom(404, {
      error: { code: "not_found", message: "Document not found.", request_id: "req-1" },
    });
    expect(error).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Document not found.",
      requestId: "req-1",
    });
  });

  it("falls back when the body is not an envelope", () => {
    expect(errorFrom(502, "<html>bad gateway</html>")).toMatchObject({ code: "server_error" });
    expect(errorFrom(400, null)).toMatchObject({ code: "request_failed" });
  });
});

describe("paths", () => {
  it("encodes project and collection segments", async () => {
    const { coll, proj } = await import("@/lib/api");
    expect(proj("acme payments")).toBe("/api/v1/projects/acme%20payments");
    expect(coll("acme", "docs/v2")).toBe("/api/v1/projects/acme/collections/docs%2Fv2");
  });
});
