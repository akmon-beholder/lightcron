/**
 * Playwright E2E tests for system-dashboard.feature (J009).
 *
 * These tests rely on:
 *   - The Lightcron scheduler running at VITE_API_BASE_URL (default: http://localhost:8000)
 *   - The web UI accessible at PLAYWRIGHT_BASE_URL (default: http://localhost:5173)
 *
 * DB state is seeded via the REST API before each test; cleaned up with cancelation.
 */

import { test, expect, type APIRequestContext } from "@playwright/test";
import axios from "axios";

const API_BASE = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const api = axios.create({ baseURL: API_BASE });

// ── Helpers ────────────────────────────────────────────────────────────────

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

// ── Dashboard: worker fleet panel ─────────────────────────────────────────

test("Dashboard shows empty state when no workers are registered", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("No workers registered")).toBeVisible();
});

test("Dashboard shows empty state when no jobs exist", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("No jobs")).toBeVisible();
});

// ── Dashboard: jobs panel ─────────────────────────────────────────────────

test("Dashboard shows pending jobs with correct status", async ({ page }) => {
  const job = await createJob();
  try {
    await page.goto("/");
    // Wait for jobs panel to load (initial fetch)
    await expect(
      page.locator("text=pending").first()
    ).toBeVisible({ timeout: 5000 });
  } finally {
    await cancelJob(job.job_id);
  }
});

// ── Dashboard: status filter ───────────────────────────────────────────────

test("Jobs panel can be filtered by status", async ({ page }) => {
  const job = await createJob();
  try {
    await page.goto("/");
    // Select "pending" from the status filter
    await page.selectOption("select", "pending");
    // Pending job should be visible
    await expect(
      page.locator("text=pending").first()
    ).toBeVisible({ timeout: 5000 });
    // Select "running" — no running jobs seeded → empty state
    await page.selectOption("select", "running");
    await expect(page.getByText("No jobs")).toBeVisible({ timeout: 5000 });
  } finally {
    await cancelJob(job.job_id);
  }
});

// ── Dashboard: auto-refresh ────────────────────────────────────────────────

test("Dashboard auto-refreshes and reflects updated job status", async ({ page }) => {
  // Create a pending job
  const job = await createJob();
  try {
    await page.goto("/");

    // Confirm job appears as pending
    await expect(
      page.locator("text=pending").first()
    ).toBeVisible({ timeout: 5000 });

    // Cancel the job (transitions to cancelled) — simulates a state change
    await cancelJob(job.job_id);

    // Select "cancelled" in the filter to verify auto-refresh shows updated state
    await page.selectOption("select", "cancelled");

    // The dashboard should auto-refresh within DASHBOARD_REFRESH_INTERVAL_MS (10s)
    // but we also wait up to 15s in test to account for timing
    await expect(
      page.locator("text=cancelled").first()
    ).toBeVisible({ timeout: 15000 });
  } finally {
    // Already cancelled above; best effort cleanup
    try { await cancelJob(job.job_id); } catch { /* ignore */ }
  }
});

// ── Navigation ────────────────────────────────────────────────────────────

test("Navigation links work correctly", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Lightcron/);

  // Click "Schedule Job" nav link
  await page.getByRole("link", { name: "Schedule Job" }).click();
  await expect(page).toHaveURL(/\/jobs\/new/);

  // Click "Dashboard" nav link
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page).toHaveURL(/\/$/);
});
