import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";
const apiBaseURL =
  process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,  // serial for DB state tests
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  webServer: process.env.CI
    ? undefined
    : {
        command: `VITE_API_BASE_URL=${apiBaseURL} npm run dev`,
        url: baseURL,
        reuseExistingServer: true,
      },
});
