import { expect, test } from "@playwright/test";

import { DOCS, PROJECT, signIn } from "../helpers";

const QUESTION = "how do I verify webhook signatures";

test.describe("retrieval playground", () => {
  test("every hit shows what each stage scored", async ({ page }) => {
    await signIn(page, "viewer");
    await page.goto(`/p/${PROJECT}/playground?collection=${DOCS}`);
    await page.getByLabel("Query").fill(QUESTION);
    await page.getByRole("button", { name: "Retrieve" }).click();
    const first = page.getByRole("article").first();
    await expect(first).toContainText("Webhooks");
    for (const stage of ["Vector", "Keyword", "Fused", "Rerank"]) {
      await expect(first.getByText(stage, { exact: true })).toBeVisible();
    }
    await expect(page.getByRole("img", { name: "Time per stage" })).toBeVisible();
    await expect(page.locator("mark").first()).toBeVisible();
    // The URL carries the request, so the result can be shared and reloaded.
    await expect(page).toHaveURL(/q=how\+do\+I\+verify\+webhook\+signatures/);
  });

  test("answers cite their sources, and a citation shows its quote", async ({ page }) => {
    await signIn(page, "viewer");
    await page.goto(
      `/p/${PROJECT}/playground?collection=${DOCS}&answer=1&q=${encodeURIComponent(QUESTION)}`,
    );
    const chip = page.getByRole("button", { name: /^Citation 1:/ }).first();
    await expect(chip).toBeVisible();
    await expect(page.getByText("extractive", { exact: true })).toBeVisible();
    await chip.click();
    await expect(page.getByRole("dialog").locator("blockquote")).toBeVisible();
  });

  test("two versions side by side show where their rankings differ", async ({ page }) => {
    await signIn(page, "viewer");
    await page.goto(
      `/p/${PROJECT}/playground?collection=${DOCS}&version=2&compare=1&q=${encodeURIComponent("instant payout fee")}`,
    );
    await expect(page.getByRole("region", { name: "Results for v2" })).toBeVisible();
    const baseline = page.getByRole("region", { name: "Results for v1" });
    await expect(baseline.getByRole("article").first()).toBeVisible();
    await expect(baseline.getByText(/in v2|Not in v2 top results/).first()).toBeVisible();
  });

  test("overrides and metadata filters change the request without a new version", async ({
    page,
  }) => {
    await signIn(page, "viewer");
    await page.goto(`/p/${PROJECT}/playground?collection=${DOCS}`);
    await page.getByLabel("Query").fill("payout schedule");
    await page.getByRole("button", { name: /Overrides/ }).click();
    await page.getByLabel("Mode").selectOption("keyword");
    await page.getByLabel("Metadata filter").fill('{"audience": "admins"}');
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Retrieve" }).click();
    await expect(page.getByText("Keyword, cross-encoder")).toBeVisible();
    const tags = page.getByRole("article").getByText("audience: admins");
    await expect(tags.first()).toBeVisible();
    expect(await page.getByRole("article").getByText("audience: developers").count()).toBe(0);
  });
});
