import { expect, test } from "@playwright/test";

import { PEOPLE, PROJECT, requirePassword, signIn } from "../helpers";

test("the owner signs in and lands on the project overview", async ({ page }) => {
  await signIn(page, "owner");
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}$`));
  await expect(page.getByRole("heading", { name: "Acme Payments", level: 1 })).toBeVisible();
  await expect(page.getByText("Retrieval quality")).toBeVisible();
  await expect(page.getByRole("link", { name: /Developer docs/ }).first()).toBeVisible();
});

test("a wrong password is refused with a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody@acme-payments.example");
  await page.getByLabel("Password").fill(`${requirePassword()}-wrong`);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email or password is incorrect.");
  await expect(page).toHaveURL(/\/login/);
});

test("signed-out visitors are sent to sign in, then back where they were going", async ({
  page,
}) => {
  await page.goto(`/p/${PROJECT}/analytics`);
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email").fill(PEOPLE.viewer.email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}/analytics`));
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
});

test("a viewer sees no editing controls", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/p/${PROJECT}/collections`);
  await expect(page.getByRole("link", { name: /Developer docs/ }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "New collection" })).toHaveCount(0);
  await page.goto(`/p/${PROJECT}/collections/developer-docs`);
  await expect(page.getByRole("button", { name: "Add sources" })).toHaveCount(0);
  await page.goto(`/p/${PROJECT}/settings`);
  await expect(page.getByRole("tab", { name: "API keys" })).toHaveCount(0);
});

test("the theme toggle switches to dark and back", async ({ page }) => {
  await signIn(page, "owner");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("menuitem", { name: "Light theme" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});
