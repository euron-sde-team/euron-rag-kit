import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

export const API_URL = process.env.API_URL ?? "http://localhost:8160";
export const WEB_URL = process.env.WEB_URL ?? "http://localhost:3160";
export const PASSWORD = process.env.DEMO_PASSWORD ?? "";
export const PROJECT = "acme-payments";
export const DOCS = "developer-docs";

export const PEOPLE = {
  owner: { email: "priya.raman@acme-payments.example", name: "Priya Raman" },
  editor: { email: "daniel.okafor@acme-payments.example", name: "Daniel Okafor" },
  viewer: { email: "sofia.lindqvist@acme-payments.example", name: "Sofia Lindqvist" },
} as const;

export type Person = keyof typeof PEOPLE;

export function requirePassword(): string {
  if (!PASSWORD) throw new Error("Set DEMO_PASSWORD (make e2e reads it from deploy/compose/.env)");
  return PASSWORD;
}

const SESSIONS = path.resolve(__dirname, ".auth");

/** Sign in through the form, exactly as a person does. */
export async function signInWithForm(page: Page, who: Person = "owner"): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE[who].email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(`/p/${PROJECT}`));
}

/**
 * A signed-in page for one demo person. The session cookie from the first form sign-in is
 * saved per role and reused by later tests: the API allows ten sign-ins a minute per
 * address, and the suites would otherwise trip that limit themselves. A stale cookie (after
 * `make down`) falls back to the form.
 */
export async function signIn(page: Page, who: Person = "owner"): Promise<void> {
  const saved = path.join(SESSIONS, `${who}.json`);
  if (existsSync(saved)) {
    await page.context().addCookies(JSON.parse(readFileSync(saved, "utf8")));
    await page.goto("/");
    await page.waitForURL(/\/(p\/[^/]+|login|welcome)/);
    if (page.url().includes(`/p/${PROJECT}`)) return;
    await page.context().clearCookies();
  }
  await signInWithForm(page, who);
  mkdirSync(SESSIONS, { recursive: true });
  writeFileSync(saved, JSON.stringify(await page.context().cookies()));
}

/** GET a project API path with the page's session; returns the parsed body. */
export async function apiGet<T>(page: Page, apiPath: string): Promise<T> {
  const response = await page.request.get(`${API_URL}/api/v1/projects/${PROJECT}${apiPath}`);
  expect(response.ok(), apiPath).toBeTruthy();
  return (await response.json()) as T;
}

export type RunRow = {
  id: string;
  label: string;
  status: string;
  is_baseline: boolean;
  pipeline_version: number;
  dataset: { slug: string };
};

/** The seeded runs of a dataset, newest first. */
export async function runsOf(page: Page, dataset: string): Promise<RunRow[]> {
  const body = await apiGet<{ items: RunRow[] }>(page, `/eval-runs?dataset=${dataset}&limit=50`);
  return body.items;
}

/** Wait until the page has settled: no pending network, fonts ready, transitions finished. */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    await document.fonts.ready;
    // Spinners and pulsing dots repeat forever; only wait for animations that end.
    const finite = document
      .getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Infinity);
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
  });
}
