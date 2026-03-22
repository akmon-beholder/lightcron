/**
 * Playwright E2E tests for job-detail.feature (J011) and dashboard navigation (AC-V2-F19).
 *
 * Tests use:
 *   - Direct DB helpers (insertJobV2, insertWorkerV2) for seeding rich job state
 *   - page.route() to mock the worker REST API (stdout/stderr endpoints)
 *   - page.route() to simulate worker offline (network abort)
 *   - page.route() to mock the scheduler API for auto-refresh scenarios
 *
 * All tests start from a clean DB state via cleanTables().
 */

import { test, expect } from "@playwright/test";
import { cleanTables, insertJobV2, insertWorkerV2 } from "./db-helpers.js";

test.beforeEach(async () => {
  await cleanTables();
});

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Mock a worker output endpoint to return a given text body.
 */
async function mockWorkerOutput(
  page: import("@playwright/test").Page,
  workerBaseUrl: string,
  jobId: string,
  stream: "stdout" | "stderr",
  responseBody: string | null,
  status = 200
) {
  const url = `${workerBaseUrl}/jobs/${jobId}/${stream}`;
  await page.route(url, (route) => {
    if (responseBody === null || status === 404) {
      route.fulfill({ status: 404, body: JSON.stringify({ detail: "Not found" }) });
    } else {
      route.fulfill({
        status,
        contentType: "text/plain",
        body: responseBody,
      });
    }
  });
}

/**
 * Mock all worker output requests to abort (simulate worker offline).
 */
async function mockWorkerOffline(
  page: import("@playwright/test").Page,
  workerBaseUrl: string
) {
  await page.route(`${workerBaseUrl}/**`, (route) => route.abort("connectionrefused"));
}

// ── @smoke: Core fields for a completed job (AC-V2-F01, AC-V2-F02) ──────────

test("@smoke Job detail page shows core fields for a completed job", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({
    command: "/usr/bin/report.sh",
    status: "completed",
    workerId: wid,
    // started_at = 2m 34s before finished_at
    startedAtOffsetSeconds: -(2 * 60 + 34),
    finishedAtOffsetSeconds: 0,
  });

  await page.goto(`/jobs/${jobId}`);

  // job_id displayed
  await expect(page.getByTestId("job-id")).toContainText(jobId, { timeout: 5000 });
  // command displayed
  await expect(page.getByText("/usr/bin/report.sh")).toBeVisible();
  // status badge
  await expect(page.locator("span").filter({ hasText: /^completed$/ })).toBeVisible();
  // actual runtime: 2m 34s
  await expect(page.getByText("2m 34s")).toBeVisible();
});

// ── @smoke: Peak memory for completed job (AC-V2-F04) ───────────────────────

test("@smoke Job detail page shows peak memory for a completed job", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({
    status: "completed",
    workerId: wid,
    peakMemoryMb: 128.5,
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByText("128.5 MB")).toBeVisible({ timeout: 5000 });
});

// ── @smoke: Live elapsed time for a running job (AC-V2-F03) ─────────────────

test("@smoke Job detail page shows live elapsed time for a running job", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({
    status: "running",
    workerId: wid,
    startedAtOffsetSeconds: -90,
    finishedAtOffsetSeconds: null,
  });

  await page.goto(`/jobs/${jobId}`);

  // Live counter should be visible (updates every second)
  const liveEl = page.getByTestId("live-elapsed");
  await expect(liveEl).toBeVisible({ timeout: 5000 });

  // Capture current value and verify it increments after 2 seconds
  const firstValue = await liveEl.textContent();
  await page.waitForTimeout(2000);
  const secondValue = await liveEl.textContent();
  expect(firstValue).not.toBe(secondValue);
});

// ── Peak memory placeholder for pending job (AC-V2-F05) ─────────────────────

test("Peak memory shows placeholder for a pending job", async ({ page }) => {
  const jobId = await insertJobV2({
    status: "pending",
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("peak-memory-placeholder")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("not yet available")).toBeVisible();
});

// ── @smoke: Stdout fetched from worker REST API (AC-V2-F06) ─────────────────

test("@smoke Job detail page fetches and shows stdout from the worker REST API", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({
    status: "completed",
    workerId: wid,
  });

  // Mock the worker stdout endpoint BEFORE navigation
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", "Hello, world!");
  // Also mock stderr to avoid 404 noise
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", null);

  // Track requests to verify URL construction
  const stdoutRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/stdout")) stdoutRequests.push(req.url());
  });

  await page.goto(`/jobs/${jobId}`);

  // Content visible in pre block
  await expect(page.getByTestId("stdout-content")).toContainText("Hello, world!", {
    timeout: 5000,
  });

  // URL was constructed correctly (AC-V2-F18)
  expect(stdoutRequests.some((u) => u === `${WORKER_BASE}/jobs/${jobId}/stdout`)).toBe(true);
});

// ── @smoke: Stderr fetched and visually distinguished (AC-V2-F08) ────────────

test("@smoke Job detail page fetches and shows stderr, visually distinguished", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({
    status: "completed",
    workerId: wid,
  });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", null);
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", "Warning: config file not found");

  await page.goto(`/jobs/${jobId}`);

  const stderrContent = page.getByTestId("stderr-content");
  await expect(stderrContent).toContainText("Warning: config file not found", {
    timeout: 5000,
  });

  // stderr block has a visually distinct label colour (red vs blue)
  const stderrLabel = page.locator("div", { hasText: /^stderr$/ }).first();
  await expect(stderrLabel).toBeVisible();
  // Colour difference is checked via CSS — confirm via computed style
  const stderrLabelColor = await stderrLabel.evaluate(
    (el) => window.getComputedStyle(el).color
  );
  // red-ish color (rgb values for #b91c1c)
  expect(stderrLabelColor).toContain("185"); // r=185 for #b91c1c
});

// ── 404 stdout → "No output" (AC-V2-F07) ────────────────────────────────────

test("Stdout block shows No output when worker returns 404", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({ status: "completed", workerId: wid });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", null, 404);
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", null, 404);

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("stdout-no-output")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("stdout-no-output")).toContainText("No output");
});

// ── 404 stderr → "No output" (AC-V2-F09) ────────────────────────────────────

test("Stderr block shows No output when worker returns 404", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({ status: "completed", workerId: wid });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", null, 404);
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", null, 404);

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("stderr-no-output")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("stderr-no-output")).toContainText("No output");
});

// ── Running job → "job in progress"; no fetch to worker (AC-V2-F14) ─────────

test("Running job shows job-in-progress placeholders and makes no worker output requests", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({
    status: "running",
    workerId: wid,
    startedAtOffsetSeconds: -10,
    finishedAtOffsetSeconds: null,
  });

  const workerOutputRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes(WORKER_BASE)) workerOutputRequests.push(req.url());
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("stdout-in-progress")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("stderr-in-progress")).toBeVisible();
  await expect(page.getByTestId("peak-memory-in-progress")).toBeVisible();

  // Give time for any erroneous requests
  await page.waitForTimeout(1000);
  expect(workerOutputRequests).toHaveLength(0);
});

// ── Worker offline → "Worker offline" (AC-V2-F17, @error-handling) ──────────

test("@error-handling Output sections show worker offline message when worker is unreachable", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({ status: "completed", workerId: wid });

  await mockWorkerOffline(page, WORKER_BASE);

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("stdout-offline")).toBeVisible({ timeout: 8000 });
  await expect(page.getByTestId("stderr-offline")).toBeVisible();
  await expect(page.getByText("Worker offline — logs unavailable").first()).toBeVisible();
});

// ── @smoke: Kill reason warning banner (AC-V2-F10) ───────────────────────────

test("@smoke Kill reason is shown prominently for a job killed for exceeding max_runtime", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({
    status: "failed",
    workerId: wid,
    killReason: "max_runtime_exceeded",
  });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", null, 404);
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", "partial stderr before kill");

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("kill-reason-banner")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("kill-reason-banner")).toContainText("max_runtime_exceeded");
  await expect(page.getByTestId("stderr-content")).toContainText("partial stderr before kill");
});

// ── Kill reason: max_memory_exceeded ────────────────────────────────────────

test("Kill reason banner shows max_memory_exceeded", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({
    status: "failed",
    workerId: wid,
    killReason: "max_memory_exceeded",
  });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", null, 404);
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", null, 404);

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("kill-reason-banner")).toBeVisible({ timeout: 5000 });
  await expect(page.getByTestId("kill-reason-banner")).toContainText("max_memory_exceeded");
});

// ── @smoke: env_vars key/value table (AC-V2-F11) ────────────────────────────

test("@smoke Job detail page shows env_vars as a key/value table", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({
    status: "completed",
    workerId: wid,
    envVars: { APP_ENV: "staging", LOG_LEVEL: "debug" },
  });

  await page.goto(`/jobs/${jobId}`);

  const table = page.getByTestId("env-vars-table");
  await expect(table).toBeVisible({ timeout: 5000 });
  await expect(table.getByText("APP_ENV")).toBeVisible();
  await expect(table.getByText("staging")).toBeVisible();
  await expect(table.getByText("LOG_LEVEL")).toBeVisible();
  await expect(table.getByText("debug")).toBeVisible();
});

// ── Empty env_vars → "No environment variables" (AC-V2-F12) ─────────────────

test("Job detail page shows empty state when env_vars is empty", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({
    status: "completed",
    workerId: wid,
    envVars: {},
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("no-env-vars")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("No environment variables")).toBeVisible();
});

// ── @error-handling: Unknown job_id → "Job not found" (AC-V2-F13) ────────────

test("@error-handling Job detail page shows error state when job is not found", async ({ page }) => {
  const fakeId = "00000000-0000-0000-0000-000000000099";

  await page.goto(`/jobs/${fakeId}`);

  await expect(page.getByTestId("job-not-found")).toBeVisible({ timeout: 5000 });
  await expect(page.getByText("Job not found")).toBeVisible();
  await expect(page.getByTestId("dashboard-link")).toBeVisible();
});

// ── @smoke: Auto-refresh updates status and fetches output (AC-V2-F15) ───────

test("@smoke Detail page auto-refreshes and fetches output once job completes", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });

  // Start as running
  const jobId = await insertJobV2({
    status: "running",
    workerId: wid,
    startedAtOffsetSeconds: -5,
    finishedAtOffsetSeconds: null,
  });

  // The first scheduler API call returns running; the second returns completed.
  // Use page.route() to intercept and control the sequence.
  let callCount = 0;
  const runningResponse = {
    job_id: jobId,
    command: "echo e2e",
    start_time: new Date().toISOString(),
    depends_on: [],
    max_runtime: null,
    max_memory: null,
    env_vars: {},
    status: "running",
    worker_id: wid,
    exit_code: null,
    kill_reason: null,
    peak_memory_mb: null,
    claimed_at: new Date().toISOString(),
    started_at: new Date(Date.now() - 5000).toISOString(),
    finished_at: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  const completedResponse = {
    ...runningResponse,
    status: "completed",
    finished_at: new Date().toISOString(),
    peak_memory_mb: 64.0,
  };

  const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  await page.route(`${apiBase}/jobs/${jobId}`, (route) => {
    callCount++;
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(callCount === 1 ? runningResponse : completedResponse),
    });
  });

  await mockWorkerOutput(page, WORKER_BASE, jobId, "stdout", "final output");
  await mockWorkerOutput(page, WORKER_BASE, jobId, "stderr", null, 404);

  await page.goto(`/jobs/${jobId}`);

  // Initially running
  await expect(page.locator("span").filter({ hasText: /^running$/ })).toBeVisible({
    timeout: 5000,
  });
  await expect(page.getByTestId("stdout-in-progress")).toBeVisible();

  // Wait for auto-refresh (JOB_DETAIL_REFRESH_INTERVAL_MS = 5s)
  await expect(page.locator("span").filter({ hasText: /^completed$/ })).toBeVisible({
    timeout: 15000,
  });

  // Output should now be fetched
  await expect(page.getByTestId("stdout-content")).toContainText("final output", {
    timeout: 8000,
  });
});

// ── base_url used to construct worker log URL (AC-V2-F18) ────────────────────

test("UI constructs worker log URL from base_url in GET /workers response", async ({ page }) => {
  const WORKER_BASE = "http://worker-01:8001";
  const wid = await insertWorkerV2({
    hostname: "worker-01",
    status: "online",
    baseUrl: WORKER_BASE,
  });
  const jobId = await insertJobV2({ status: "completed", workerId: wid });

  const capturedUrls: string[] = [];
  await page.route(`${WORKER_BASE}/**`, (route) => {
    capturedUrls.push(route.request().url());
    route.fulfill({
      status: 200,
      contentType: "text/plain",
      body: "output content",
    });
  });

  await page.goto(`/jobs/${jobId}`);

  await expect(page.getByTestId("stdout-content")).toBeVisible({ timeout: 5000 });

  expect(capturedUrls).toContain(`${WORKER_BASE}/jobs/${jobId}/stdout`);
  expect(capturedUrls).toContain(`${WORKER_BASE}/jobs/${jobId}/stderr`);
});

// ── Dashboard job row click navigates to detail page (AC-V2-F19) ─────────────

test("Dashboard job row click navigates to job detail page", async ({ page }) => {
  const wid = await insertWorkerV2({ hostname: "worker-01", status: "online" });
  const jobId = await insertJobV2({ status: "completed", workerId: wid });

  await page.goto("/");

  // Click the job ID link in the row
  const jobLink = page.getByRole("link", { name: new RegExp(jobId.slice(0, 8)) });
  await expect(jobLink).toBeVisible({ timeout: 5000 });
  await jobLink.click();

  await expect(page).toHaveURL(new RegExp(`/jobs/${jobId}`));
  await expect(page.getByTestId("job-id")).toContainText(jobId, { timeout: 5000 });
});
