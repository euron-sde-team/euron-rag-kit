/**
 * README screenshots (1440x900 at 2x) and tour frames, from the seeded demo project.
 * Every image shows the real stack: nothing here is mocked.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { DOCS, PROJECT, runsOf, settle, signIn } from "../helpers";

const SHOTS = path.resolve(__dirname, "../../docs/assets/screenshots");
const FRAMES = path.resolve(__dirname, "../.capture/frames");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(FRAMES, { recursive: true });

const BASE = `/p/${PROJECT}`;
let frame = 0;

async function shot(page: Page, name: string): Promise<void> {
  await settle(page);
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function tourFrame(page: Page, holdMs = 1800): Promise<void> {
  frame += 1;
  const file = path.join(FRAMES, `${String(frame).padStart(3, "0")}-${holdMs}.png`);
  await page.screenshot({ path: file, scale: "css" });
}

test.describe.configure({ mode: "serial" });
// Captures run on a busy laptop as often as on CI: allow slow answers rather than flake.
test.setTimeout(300_000);

test("sign-in page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("Retrieval you can measure.")).toBeVisible();
  await shot(page, "01-sign-in");
  await tourFrame(page, 1400);
});

test("collections, versions, the playground, evaluations, analytics and keys", async ({ page }) => {
  await signIn(page, "owner");
  const golden = await runsOf(page, "support-golden");
  const baseline = golden.find((run) => run.is_baseline) ?? golden[0]!;
  const v1 = golden.find((run) => run.pipeline_version === 1) ?? golden.at(-1)!;
  const v3 = golden.find((run) => run.pipeline_version === 3);

  await page.goto(BASE);
  await expect(page.locator(".recharts-line").first()).toBeVisible();
  await shot(page, "02-overview");
  await tourFrame(page, 2200);

  await page.goto(`${BASE}/collections/${DOCS}`);
  await expect(
    page.getByRole("table", { name: "Documents" }).getByText("Ready").first(),
  ).toBeVisible();
  await shot(page, "03-documents");
  await tourFrame(page, 1800);

  await page.goto(`${BASE}/collections/${DOCS}/pipelines`);
  await expect(page.getByText("Serving")).toBeVisible();
  await shot(page, "04-pipelines");
  await tourFrame(page, 2000);

  await page.goto(`${BASE}/collections/${DOCS}/pipelines/3`);
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await page
    .getByRole("button", { name: /context window/ })
    .first()
    .click();
  // The configuration fills the first screen; the chunks and their sizes are the story here.
  await page.evaluate(() => {
    const title = [...document.querySelectorAll("h3")].find((h) => h.textContent === "Chunks");
    title?.closest(".rounded-xl")?.scrollIntoView({ block: "start" });
    document.querySelector("main")?.scrollBy(0, -24);
  });
  await shot(page, "05-version-chunks");

  await page.goto(`${BASE}/collections/${DOCS}/pipelines/new?from=2`);
  await page.getByLabel("Name").fill("Smaller chunks, same reranker");
  await page.getByLabel("Chunk tokens").fill("192");
  await expect(page.getByText("Builds a new index.")).toBeVisible();
  await expect(page.getByText(/^Mean$/)).toBeVisible();
  await page.waitForTimeout(900);
  // Typing scrolled the form; show it from the top, beside the index notice and the preview.
  await page.evaluate(() => {
    const title = [...document.querySelectorAll("h2")].find(
      (h) => h.textContent === "New pipeline version",
    );
    title?.scrollIntoView({ block: "start" });
    document.querySelector("main")?.scrollBy(0, -24);
  });
  await shot(page, "06-new-version-preview");
  await tourFrame(page, 2200);

  const query = encodeURIComponent("how do I verify webhook signatures");
  await page.goto(`${BASE}/playground?collection=${DOCS}&q=${query}`);
  await expect(page.getByRole("article").first()).toBeVisible();
  await shot(page, "07-playground-stages");
  await tourFrame(page, 2600);

  await page.goto(
    `${BASE}/playground?collection=${DOCS}&answer=1&q=${encodeURIComponent("How do I rotate API keys without downtime?")}`,
  );
  const chip = page.getByRole("button", { name: /^Citation 1:/ }).first();
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(page.getByRole("dialog").locator("blockquote")).toBeVisible();
  await shot(page, "08-playground-answer");
  await tourFrame(page, 2600);
  await page.keyboard.press("Escape");

  await page.goto(
    `${BASE}/playground?collection=${DOCS}&version=2&compare=1&q=${encodeURIComponent("instant payout fee")}`,
  );
  await expect(
    page.getByRole("region", { name: "Results for v1" }).getByRole("article").first(),
  ).toBeVisible();
  await shot(page, "09-playground-compare");
  await tourFrame(page, 2400);

  await page.goto(`${BASE}/evaluations`);
  await expect(
    page.getByRole("table", { name: "Evaluation runs" }).getByText("Baseline"),
  ).toBeVisible();
  await shot(page, "10-evaluations");
  await tourFrame(page, 2000);

  await page.goto(`${BASE}/evaluations/runs/${baseline.id}`);
  await expect(page.getByText(/^(Passes|Fails)$/)).toBeVisible();
  await shot(page, "11-run");
  await tourFrame(page, 2200);

  const compared = v3 ? `${v1.id},${baseline.id},${v3.id}` : `${v1.id},${baseline.id}`;
  await page.goto(`${BASE}/evaluations/compare?runs=${compared}`);
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(page, "12-compare");
  await tourFrame(page, 2600);

  await page.goto(`${BASE}/evaluations/datasets/support-golden`);
  await expect(page.locator(".recharts-line").first()).toBeVisible();
  await shot(page, "13-dataset");

  await page.goto(`${BASE}/analytics`);
  await expect(page.locator(".recharts-area").first()).toBeVisible();
  await shot(page, "14-analytics");
  await tourFrame(page, 2200);

  await page.goto(`${BASE}/settings`);
  await page.getByRole("tab", { name: "API keys" }).click();
  await expect(page.getByText("CI evaluation gate")).toBeVisible();
  // The clicked tab keeps a keyboard focus ring: drop it, the picture is of the page.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await shot(page, "15-api-keys");
  await tourFrame(page, 1800);
});

test("dark theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await signIn(page, "owner");
  const golden = await runsOf(page, "support-golden");
  const baseline = golden.find((run) => run.is_baseline) ?? golden[0]!;
  const v1 = golden.find((run) => run.pipeline_version === 1) ?? golden.at(-1)!;
  await page.goto(`${BASE}/evaluations/compare?runs=${v1.id},${baseline.id}`);
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  await shot(page, "16-dark-compare");
  const query = encodeURIComponent("how do I verify webhook signatures");
  await page.goto(`${BASE}/playground?collection=${DOCS}&q=${query}`);
  await expect(page.getByRole("article").first()).toBeVisible();
  await shot(page, "17-dark-playground");
});
