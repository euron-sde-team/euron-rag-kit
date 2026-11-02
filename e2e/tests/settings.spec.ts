import { expect, test } from "@playwright/test";

import { API_URL, DOCS, PROJECT, signIn } from "../helpers";

test.describe("settings, members and API keys", () => {
  test("members are listed with their roles", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/settings`);
    await page.getByRole("tab", { name: "Members" }).click();
    const panel = page.getByRole("tabpanel");
    for (const name of ["Priya Raman", "Daniel Okafor", "Sofia Lindqvist"]) {
      await expect(panel.getByText(name)).toBeVisible();
    }
  });

  test("a new API key is shown once, works against the API, and can be revoked", async ({
    page,
    request,
  }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/settings`);
    await page.getByRole("tab", { name: "API keys" }).click();
    await expect(page.getByText("Docs assistant (production)")).toBeVisible();
    await page.getByRole("button", { name: "Create key" }).click();
    const dialog = page.getByRole("dialog", { name: "Create an API key" });
    await dialog.getByLabel("Name").fill("e2e notebook");
    await dialog.getByRole("button", { name: "Create key" }).click();
    const shown = page.getByRole("dialog", { name: "Copy your key now" });
    const key = (await shown.getByLabel("API key").textContent())?.trim() ?? "";
    expect(key).toMatch(/^rgk_[a-z2-7]{10}_/);
    await expect(shown.getByLabel("Python example")).toContainText(key);

    const response = await request.post(
      `${API_URL}/api/v1/projects/${PROJECT}/collections/${DOCS}/query`,
      {
        headers: { authorization: `Bearer ${key}` },
        data: { query: "rate limit in live mode" },
      },
    );
    expect(response.status()).toBe(200);
    expect((await response.json()).hits.length).toBeGreaterThan(0);

    await shown.getByRole("button", { name: "Done" }).click();
    const row = page.getByRole("listitem").filter({ hasText: "e2e notebook" });
    await row.getByRole("button", { name: "Revoke" }).click();
    await expect(row.getByText("Revoked")).toBeVisible();
    const after = await request.post(
      `${API_URL}/api/v1/projects/${PROJECT}/collections/${DOCS}/query`,
      {
        headers: { authorization: `Bearer ${key}` },
        data: { query: "rate limit in live mode" },
      },
    );
    expect(after.status()).toBe(401);
  });

  test("the activity trail records who changed what", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/settings`);
    await page.getByRole("tab", { name: "Activity" }).click();
    await expect(page.getByText("created v2 of developer-docs")).toBeVisible();
  });
});
