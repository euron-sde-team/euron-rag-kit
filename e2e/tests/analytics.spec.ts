import { expect, test } from "@playwright/test";

import { PROJECT, signIn } from "../helpers";

test("analytics show traffic, latency, misses and the top queries", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/p/${PROJECT}/analytics`);
  await expect(page.getByText("Requests per day")).toBeVisible();
  await expect(page.getByText("Zero-hit rate").first()).toBeVisible();
  const top = page.getByRole("table", { name: "Top queries" });
  await expect(top.getByRole("row").nth(1)).toBeVisible();

  await page.getByLabel("Collection").selectOption("support-playbooks");
  await expect(top.getByRole("cell", { name: "Support playbooks" }).first()).toBeVisible();

  // A top query opens in the playground, ready to inspect.
  await top.getByRole("link").first().click();
  await expect(page).toHaveURL(/\/playground\?collection=support-playbooks&q=/);
  await expect(page.getByRole("article").first()).toBeVisible();
});
