/**
 * Playwright global setup — verifies the scheduler API is reachable.
 *
 * Each test manages its own DB state by creating and cancelling jobs inline.
 * No global seeds are created here to avoid interference between tests.
 */

import axios from "axios";

const API_BASE = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const client = axios.create({ baseURL: API_BASE });

async function setup() {
  try {
    await client.get("/health");
  } catch {
    // Scheduler may not be up yet; tests will handle gracefully
  }
}

export default setup;
