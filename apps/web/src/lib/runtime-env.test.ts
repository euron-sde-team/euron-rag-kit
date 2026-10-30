import { describe, expect, it } from "vitest";

import { serializeEnv } from "@/lib/runtime-env";

describe("serializeEnv", () => {
  it("emits the configured values and trims trailing slashes", () => {
    const script = serializeEnv({ API_URL: "https://api.example.com/", PRODUCT_NAME: "Acme Docs" });
    expect(script).toBe(
      'window.__RAGKIT__={"apiUrl":"https://api.example.com","productName":"Acme Docs"};',
    );
  });

  it("falls back to local defaults", () => {
    expect(serializeEnv({})).toContain('"apiUrl":"http://localhost:8160"');
  });

  it("cannot close the script tag it is served in", () => {
    const script = serializeEnv({ PRODUCT_NAME: "</script><script>alert(1)</script>" });
    expect(script).not.toContain("</script>");
  });
});
