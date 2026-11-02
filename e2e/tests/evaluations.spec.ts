import { expect, test } from "@playwright/test";

import { PROJECT, runsOf, signIn } from "../helpers";

test.describe("evaluations", () => {
  test("the runs table shows the seeded experiments and the baseline", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/evaluations`);
    const table = page.getByRole("table", { name: "Evaluation runs" });
    await expect(
      table.getByRole("link", { name: /v2 recursive, hybrid \+ cross-encoder/ }).first(),
    ).toBeVisible();
    await expect(table.getByText("Baseline")).toBeVisible();
    await expect(table.getByRole("link", { name: /keyword only \(ablation\)/ })).toBeVisible();
  });

  test("two runs compare metric by metric, setting by setting and question by question", async ({
    page,
  }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/evaluations`);
    await page.getByRole("combobox", { name: "Dataset" }).selectOption("support-golden");
    await page.getByRole("checkbox", { name: /Select v1 fixed, vector/ }).check();
    await page
      .getByRole("checkbox", { name: /Select v2 recursive, hybrid \+ cross-encoder/ })
      .check();
    await page.getByRole("button", { name: "Compare" }).click();
    await expect(page).toHaveURL(/\/evaluations\/compare\?runs=/);
    await expect(page.getByRole("heading", { name: "Compare runs" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Configuration differences" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "chunking.strategy" })).toBeVisible();
    await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
    await page.getByRole("button", { name: /improved/ }).click();
    await expect(page.getByText("improved", { exact: true }).first()).toBeVisible();
  });

  test("a run shows its metrics, the gate verdict and each question's evidence", async ({
    page,
  }) => {
    await signIn(page, "owner");
    const runs = await runsOf(page, "support-golden");
    const baseline = runs.find((run) => run.is_baseline);
    expect(baseline).toBeDefined();
    await page.goto(`/p/${PROJECT}/evaluations/runs/${baseline!.id}`);
    await expect(page.getByText("MRR", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Release gate")).toBeVisible();
    await expect(page.getByText(/^(Passes|Fails)$/)).toBeVisible();
    await page.getByRole("button", { name: "Show details" }).first().click();
    await expect(page.getByText("Expected sources")).toBeVisible();
    await expect(page.getByText("Retrieved", { exact: true })).toBeVisible();
  });

  test("an editor runs the smoke set and the worker scores it", async ({ page }) => {
    await signIn(page, "editor");
    await page.goto(`/p/${PROJECT}/evaluations`);
    await page.getByRole("button", { name: "New run" }).click();
    const dialog = page.getByRole("dialog", { name: "Start an evaluation run" });
    await dialog.getByLabel("Dataset").selectOption("smoke");
    await dialog.getByLabel("Label").fill("e2e smoke check");
    await dialog.getByRole("button", { name: "Start run" }).click();
    await expect(page).toHaveURL(/\/evaluations\/runs\//);
    await expect(page.getByRole("heading", { name: "e2e smoke check" })).toBeVisible();
    await expect(page.getByText("Completed")).toBeVisible({ timeout: 110_000 });
    await expect(page.getByText(/Hit rate@5/).first()).toBeVisible();
  });

  test("a dataset shows its questions, history and gate thresholds", async ({ page }) => {
    await signIn(page, "owner");
    await page.goto(`/p/${PROJECT}/evaluations/datasets/support-golden`);
    await expect(page.getByRole("heading", { name: "Support golden set" })).toBeVisible();
    await expect(page.getByLabel("Hit rate at least")).toHaveValue("0.85");
    await expect(page.getByLabel("Largest drop against the baseline")).toHaveValue("0.03");
    const questions = page.getByRole("table", { name: "Dataset questions" });
    await expect(questions.getByRole("row")).toHaveCount(37);
  });
});
