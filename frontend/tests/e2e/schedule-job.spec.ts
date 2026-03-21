/**
 * Playwright E2E tests for schedule-job-ui.feature (J010).
 */

import { test, expect } from "@playwright/test";

function futureDateTime(offsetMinutes: number): string {
  const d = new Date(Date.now() + offsetMinutes * 60_000);
  // datetime-local input format: YYYY-MM-DDTHH:MM
  return d.toISOString().slice(0, 16);
}

function pastDateTime(offsetMinutes: number): string {
  const d = new Date(Date.now() - offsetMinutes * 60_000);
  return d.toISOString().slice(0, 16);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/jobs/new");
  await expect(page.getByRole("heading", { name: "Schedule a Job" })).toBeVisible();
});

// ── Happy path ────────────────────────────────────────────────────────────

test("User submits a valid job with required fields only", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Job scheduled successfully!")).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByText("Job ID:")).toBeVisible();
  await expect(page.getByRole("link", { name: "View job detail →" })).toBeVisible();
});

test("User submits a job with all optional fields populated", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page.locator('input[type="number"]').nth(0).fill("300");
  await page.locator('input[type="number"]').nth(1).fill("512");
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Job scheduled successfully!")).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByText("Job ID:")).toBeVisible();
});

// ── Client-side validation ────────────────────────────────────────────────

test("Form shows validation error when command is missing", async ({ page }) => {
  // Leave command empty
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Command is required.")).toBeVisible();
  await expect(page.getByText("Job scheduled successfully!")).not.toBeVisible();
});

test("Form shows validation error when start_time is in the past", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(pastDateTime(10));
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Start time must be in the future.")).toBeVisible();
  await expect(page.getByText("Job scheduled successfully!")).not.toBeVisible();
});

test("Form shows validation error for non-positive max_runtime", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page.locator('input[type="number"]').nth(0).fill("-1");
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Max runtime must be greater than 0.")).toBeVisible();
  await expect(page.getByText("Job scheduled successfully!")).not.toBeVisible();
});

test("Form shows validation error for non-positive max_memory", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page.locator('input[type="number"]').nth(1).fill("0");
  await page.getByRole("button", { name: "Schedule Job" }).click();

  await expect(page.getByText("Max memory must be greater than 0.")).toBeVisible();
  await expect(page.getByText("Job scheduled successfully!")).not.toBeVisible();
});

// ── Server-side validation passthrough ────────────────────────────────────

test("Form displays server error for unknown depends_on UUID", async ({ page }) => {
  await page.getByPlaceholder("/usr/bin/my-script.sh").fill("/usr/bin/my-script.sh");
  await page.locator('input[type="datetime-local"]').fill(futureDateTime(5));
  await page
    .getByPlaceholder("Optional — e.g. uuid1, uuid2")
    .fill("00000000-0000-0000-0000-000000000000");
  await page.getByRole("button", { name: "Schedule Job" }).click();

  // Server returns 422; the form should show an error message
  await expect(
    page.locator("text=/depends_on|unknown|not found/i").first()
  ).toBeVisible({ timeout: 10000 });

  // Form stays on screen
  await expect(
    page.getByRole("heading", { name: "Schedule a Job" })
  ).toBeVisible();
});
