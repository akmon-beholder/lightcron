/**
 * Playwright E2E tests for system-dashboard.feature (J009).
 *
 * DB state is seeded before each test via:
 *   - REST API (POST /jobs, POST /jobs/:id/cancel) for states the API supports
 *   - Direct DB insert (db-helpers.ts) for workers and terminal job statuses
 *
 * cleanTables() runs before every test so each test starts from a known empty state.
 */

import { test, expect } from "@playwright/test";
import axios from "axios";
import { cleanTables, insertWorker, insertJob } from "./db-helpers.js";

const API_BASE = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const api = axios.create({ baseURL: API_BASE });

async function createJob(overrides: Record<string, unknown> = {}) {
  const { data } = await api.post("/jobs", {
    command: "echo e2e-seed",
    start_time: new Date(Date.now() + 300_000).toISOString(),
    ...overrides,
  });
  return data as { job_id: string; status: string };
}

async function cancelJob(jobId: string) {
  try {
    await api.post(`/jobs/${jobId}/cancel`);
  } catch {
    // best effort
  }
}

test.beforeEach(async () => {
  await cleanTables();
});

// ── Worker fleet panel ─────────────────────────────────────────────────────

test("Dashboard shows empty state when no workers are registered", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("No workers registered")).toBeVisible();
});

test("Dashboard shows online workers with their running job counts", async ({ page }) => {
  const wid1 = await insertWorker({ hostname: "worker-01", status: "online" });
  const wid2 = await insertWorker({ hostname: "worker-02", status: "online" });
  await insertJob({ status: "running", workerId: wid1 });
  await insertJob({ status: "running", workerId: wid1 });

  await page.goto("/");

  const row1 = page.locator("tr", { hasText: "worker-01" });
  const row2 = page.locator("tr", { hasText: "worker-02" });

  await expect(row1).toBeVisible({ timeout: 5000 });
  await expect(row1.locator("span").filter({ hasText: /^online$/ })).toBeVisible();
  // Running Jobs is the 4th column (last td)
  await expect(row1.locator("td").last()).toHaveText("2");

  await expect(row2).toBeVisible();
  await expect(row2.locator("span").filter({ hasText: /^online$/ })).toBeVisible();
  await expect(row2.locator("td").last()).toHaveText("0");
});

test("Dashboard shows an offline worker", async ({ page }) => {
  await insertWorker({ hostname: "worker-03", status: "offline" });

  await page.goto("/");

  const row = page.locator("tr", { hasText: "worker-03" });
  await expect(row).toBeVisible({ timeout: 5000 });
  await expect(row.locator("span").filter({ hasText: /^offline$/ })).toBeVisible();
});

// ── Jobs panel ─────────────────────────────────────────────────────────────

test("Dashboard shows empty state when no jobs exist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("No jobs")).toBeVisible();
});

test("Dashboard shows pending jobs with correct status", async ({ page }) => {
  const job = await createJob();
  try {
    await page.goto("/");
    await expect(
      page.locator("span").filter({ hasText: /^pending$/ }).first()
    ).toBeVisible({ timeout: 5000 });
  } finally {
    await cancelJob(job.job_id);
  }
});

test("Dashboard shows running, completed, and failed jobs", async ({ page }) => {
  const wid = await insertWorker({ hostname: "worker-01" });
  await insertJob({ status: "running", workerId: wid });
  await insertJob({ status: "completed", workerId: wid });
  await insertJob({ status: "failed", workerId: wid });

  await page.goto("/");

  await expect(
    page.locator("span").filter({ hasText: /^running$/ }).first()
  ).toBeVisible({ timeout: 5000 });
  await expect(
    page.locator("span").filter({ hasText: /^completed$/ }).first()
  ).toBeVisible();
  await expect(
    page.locator("span").filter({ hasText: /^failed$/ }).first()
  ).toBeVisible();
});

// ── Status filter ──────────────────────────────────────────────────────────

test("Jobs panel can be filtered by status", async ({ page }) => {
  const job = await createJob();
  try {
    await page.goto("/");
    await page.selectOption("select", "pending");
    await expect(
      page.locator("span").filter({ hasText: /^pending$/ }).first()
    ).toBeVisible({ timeout: 5000 });
    await page.selectOption("select", "running");
    await expect(page.getByText("No jobs")).toBeVisible({ timeout: 5000 });
  } finally {
    await cancelJob(job.job_id);
  }
});

test("Jobs panel filter shows running jobs and hides completed jobs", async ({ page }) => {
  const wid = await insertWorker({ hostname: "worker-01" });
  await insertJob({ status: "running", workerId: wid, command: "echo running-job" });
  await insertJob({ status: "completed", workerId: wid, command: "echo completed-job" });

  await page.goto("/");

  await page.selectOption("select", "running");
  await expect(
    page.locator("span").filter({ hasText: /^running$/ }).first()
  ).toBeVisible({ timeout: 5000 });
  await expect(
    page.locator("span").filter({ hasText: /^completed$/ })
  ).toHaveCount(0);
});

// ── Auto-refresh ───────────────────────────────────────────────────────────

test("Dashboard auto-refreshes and reflects updated job status", async ({ page }) => {
  const job = await createJob();
  try {
    await page.goto("/");
    await expect(
      page.locator("span").filter({ hasText: /^pending$/ }).first()
    ).toBeVisible({ timeout: 5000 });

    await cancelJob(job.job_id);
    await page.selectOption("select", "cancelled");

    await expect(
      page.locator("span").filter({ hasText: /^cancelled$/ }).first()
    ).toBeVisible({ timeout: 15000 });
  } finally {
    try { await cancelJob(job.job_id); } catch { /* ignore */ }
  }
});

// ── Navigation ─────────────────────────────────────────────────────────────

test("Navigation links work correctly", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Lightcron/);

  await page.getByRole("link", { name: "Schedule Job" }).click();
  await expect(page).toHaveURL(/\/jobs\/new/);

  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page).toHaveURL(/\/$/);
});
