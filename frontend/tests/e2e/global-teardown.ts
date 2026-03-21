/**
 * Playwright global teardown — cancels seeded jobs created in global-setup.
 */

import axios from "axios";

const API_BASE = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const client = axios.create({ baseURL: API_BASE });

async function teardown() {
  const pendingId = process.env.E2E_PENDING_JOB_ID;
  if (pendingId) {
    try {
      await client.post(`/jobs/${pendingId}/cancel`);
    } catch {
      // Best effort
    }
  }
}

export default teardown;
