import { expect, test } from "@playwright/test";

import { DOCS, PROJECT, apiGet, signIn } from "../helpers";

test.describe("collections and documents", () => {
  test("the collections page lists both corpora with their active versions", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/collections`);
    const docs = page.getByRole("link", { name: /Developer docs/ }).first();
    await expect(docs).toBeVisible();
    await expect(page.getByRole("link", { name: /Support playbooks/ }).first()).toBeVisible();
    await expect(page.getByText("Hybrid RRF").first()).toBeVisible();
  });

  test("documents show their status, and filtering narrows the list", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/collections/${DOCS}`);
    const table = page.getByRole("table", { name: "Documents" });
    await expect(table.getByRole("row")).toHaveCount(17);
    await expect(table.getByText("Ready").first()).toBeVisible();
    await page.getByLabel("Filter documents").fill("webhook");
    await expect(table.getByRole("row")).toHaveCount(2);
    await expect(table.getByRole("link", { name: "Webhooks" })).toBeVisible();
  });

  test("a document shows its parsed sections and every index it is in", async ({ page }) => {
    await signIn(page, "owner");
    const list = await apiGet<{ items: { id: string; title: string }[] }>(
      page,
      `/collections/${DOCS}/documents?q=Service%20Level`,
    );
    const pdf = list.items[0];
    expect(pdf).toBeDefined();
    await page.goto(`/p/${PROJECT}/collections/${DOCS}/documents/${pdf!.id}`);
    await expect(page.getByRole("heading", { name: pdf!.title })).toBeVisible();
    await expect(page.getByText("Parsed sections")).toBeVisible();
    await expect(page.getByText(/Page 1/).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "View chunks" }).first()).toBeVisible();
  });

  test("an editor adds a text source and it becomes ready in every index", async ({ page }) => {
    await signIn(page, "editor");
    await page.goto(`/p/${PROJECT}/collections/${DOCS}`);
    await page.getByRole("button", { name: "Add sources" }).click();
    const dialog = page.getByRole("dialog", { name: "Add sources" });
    await dialog.getByRole("tab", { name: "Text" }).click();
    await dialog.getByLabel("Title").fill("Payout holds FAQ");
    await dialog
      .getByRole("textbox", { name: "Text", exact: true })
      .fill(
        "# Payout holds\n\nA payout is held for review when the account changes its bank details.",
      );
    await dialog.getByRole("button", { name: "Add", exact: true }).click();
    await expect(dialog).toBeHidden();
    await page.getByLabel("Filter documents").fill("Payout holds");
    const row = page.getByRole("row", { name: /Payout holds FAQ/ });
    await expect(row.getByText("Ready")).toBeVisible({ timeout: 90_000 });

    await row.getByRole("button", { name: /Actions for/ }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await expect(page.getByRole("row", { name: /Payout holds FAQ/ })).toHaveCount(0);
  });
});
