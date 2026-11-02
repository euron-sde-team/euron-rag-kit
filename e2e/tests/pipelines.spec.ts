import { expect, test } from "@playwright/test";

import { DOCS, PROJECT, signIn } from "../helpers";

const BASE = `/p/${PROJECT}/collections/${DOCS}/pipelines`;

test.describe("pipeline versions", () => {
  test("versions list their stages, index state and which one serves", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(BASE);
    await expect(
      page.getByRole("link", { name: "Structure-aware hybrid with reranking" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Baseline: fixed windows, vector only" }),
    ).toBeVisible();
    await expect(page.getByText("Serving")).toHaveCount(1);
    await expect(page.getByText("Index ready").first()).toBeVisible();
  });

  test("a version shows its configuration, size histogram and chunks", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`${BASE}/3`);
    await expect(page.getByRole("heading", { name: "Sentence windows" })).toBeVisible();
    await expect(page.getByText("Window sentences")).toBeVisible();
    await expect(page.getByText(/fingerprint [0-9a-f]{16}/)).toBeVisible();
    await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
    const window = page.getByRole("button", { name: /context window/ }).first();
    await window.click();
    await expect(
      page.getByRole("button", { name: "Hide the context window" }).first(),
    ).toBeVisible();
  });

  test("changing only the reranker reuses the index; new chunking builds one", async ({ page }) => {
    await signIn(page, "editor");
    await page.goto(`${BASE}/new?from=2`);
    // The notice names the newest version that already uses the index: v2 on a fresh stack,
    // a later reranker-only version once this test has run before.
    const reuse = page.getByText(/Reuses the index of v\d+\./);
    await expect(reuse).toBeVisible();
    await expect(page.getByText(/^Chunks$/).first()).toBeVisible();

    await page.getByLabel("Chunk tokens").fill("192");
    await expect(page.getByText("Builds a new index.")).toBeVisible();
    await page.getByLabel("Chunk tokens").fill("256");
    await expect(reuse).toBeVisible();

    await page.getByLabel("Reranker").selectOption("lexical");
    await page.getByLabel("Name").fill("Lexical rerank experiment");
    await page.getByRole("button", { name: "Create version" }).click();
    await expect(page).toHaveURL(new RegExp(`${BASE}/\\d+$`));
    await expect(page.getByRole("heading", { name: "Lexical rerank experiment" })).toBeVisible();
    await expect(page.getByText(/Shared with v2/)).toBeVisible();
  });

  test("an invalid draft explains what to fix before it can be created", async ({ page }) => {
    await signIn(page, "editor");
    await page.goto(`${BASE}/new?from=2`);
    await page.getByLabel("Name").fill("Too much overlap");
    await page.getByLabel("Overlap tokens").fill("200");
    await expect(page.getByText("Overlap can be at most half the chunk size.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create version" })).toBeDisabled();
  });
});
