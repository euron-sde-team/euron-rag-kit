import { expect, test } from "@playwright/test";

import {
  API_URL,
  PEOPLE,
  PROJECT,
  WEB_URL,
  requirePassword,
  signIn,
  signInWithForm,
} from "../helpers";

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
  // Next.js keeps an empty role="alert" route announcer in every page: pick ours by its text.
  await expect(
    page.getByRole("alert").filter({ hasText: "Email or password is incorrect." }),
  ).toBeVisible();
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

test("a person changes their password, signs in with it, and the demo account is restored", async ({
  page,
}) => {
  const original = requirePassword();
  const changed = `${original}-changed`;
  await signInWithForm(page, "viewer");
  try {
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Change password" }).click();
    const dialog = page.getByRole("dialog", { name: "Change your password" });
    await dialog.getByLabel("Current password").fill(original);
    await dialog.getByLabel("New password", { exact: true }).fill(changed);
    await dialog.getByLabel("Confirm the new password").fill(changed);
    await dialog.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText(/Password changed/)).toBeVisible();
    await expect(dialog).toBeHidden();

    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel("Email").fill(PEOPLE.viewer.email);
    await page.getByLabel("Password").fill(changed);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}`));
  } finally {
    // Leave the shared demo account as it was found, even when an assertion above failed.
    // The cookie session only accepts unsafe requests that name the web app as their origin.
    const origin = { origin: WEB_URL };
    const login = await page.request.post(`${API_URL}/api/v1/auth/login`, {
      headers: origin,
      data: { email: PEOPLE.viewer.email, password: changed },
    });
    if (login.ok()) {
      await page.request.post(`${API_URL}/api/v1/auth/password`, {
        headers: origin,
        data: { current_password: changed, new_password: original },
      });
    }
  }
});
