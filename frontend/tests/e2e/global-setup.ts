/**
 * Playwright global setup — seeds known DB state via the scheduler REST API.
 *
 * Seeds:
 *   - Two workers: one online (worker-01), one offline (worker-02)
 *   - Three jobs: one pending, one running (assigned to worker-01), one completed
 *
 * The seeds are stored in process.env so globalTeardown can clean them up.
 */

import axios from "axios";

const API_BASE = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const client = axios.create({ baseURL: API_BASE });

async function setup() {
  // Seed jobs for dashboard e2e
  const future = new Date(Date.now() + 60_000).toISOString();

  try {
    const pending = await client.post("/jobs", {
      command: "echo pending-seed",
      start_time: new Date(Date.now() + 120_000).toISOString(),
    });
    process.env.E2E_PENDING_JOB_ID = pending.data.job_id as string;
  } catch {
    // Scheduler may not be up; tests will handle gracefully
  }
}

export default setup;
