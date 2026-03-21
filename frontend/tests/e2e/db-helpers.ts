/**
 * Direct PostgreSQL helpers for Playwright tests.
 *
 * The REST API can only create pending jobs and cancel them. Tests that need
 * workers or jobs in running/completed/failed states seed the DB directly,
 * matching the approach used by the Python BDD tests.
 *
 * Uses the `pg` package (Node postgres client). Accepts the same DATABASE_URL
 * that Python tests use — strips the `+asyncpg` dialect prefix if present.
 */

import { Client } from "pg";

const RAW_URL =
  process.env.DATABASE_URL ??
  "postgresql://lightcron:lightcron@localhost:5432/lightcron";

// Strip SQLAlchemy dialect suffix so the plain pg client can parse the URL.
const DB_URL = RAW_URL.replace(/\+\w+(?=:\/\/)/, "");

async function withClient<T>(fn: (client: Client) => Promise<T>): Promise<T> {
  const client = new Client({ connectionString: DB_URL });
  await client.connect();
  try {
    return await fn(client);
  } finally {
    await client.end();
  }
}

export async function cleanTables(): Promise<void> {
  await withClient(async (client) => {
    await client.query("DELETE FROM jobs");
    await client.query("DELETE FROM worker_status");
  });
}

export async function insertWorker(opts: {
  hostname: string;
  status?: "online" | "offline";
  lastSeenOffsetSeconds?: number;
}): Promise<string> {
  const { hostname, status = "online", lastSeenOffsetSeconds = 0 } = opts;
  return withClient(async (client) => {
    const res = await client.query(
      `INSERT INTO worker_status (hostname, status, last_seen, registered_at)
       VALUES ($1, CAST($2 AS worker_status_enum),
               now() - $3 * interval '1 second',
               now() - $3 * interval '1 second')
       RETURNING worker_id`,
      [hostname, status, lastSeenOffsetSeconds]
    );
    return res.rows[0].worker_id as string;
  });
}

export async function insertJob(opts: {
  command?: string;
  status: string;
  workerId?: string | null;
  startTimeOffsetSeconds?: number;
}): Promise<string> {
  const {
    command = "echo e2e-test",
    status,
    workerId = null,
    startTimeOffsetSeconds = -10,
  } = opts;
  return withClient(async (client) => {
    const res = await client.query(
      `INSERT INTO jobs (
         command, start_time, status, worker_id, started_at, finished_at
       ) VALUES (
         $1,
         now() + $2 * interval '1 second',
         CAST($3 AS job_status),
         $4,
         CASE WHEN $3 IN ('running','completed','failed','lost','cancelled')
              THEN now() - interval '5 seconds' ELSE NULL END,
         CASE WHEN $3 IN ('completed','failed')
              THEN now() ELSE NULL END
       )
       RETURNING job_id`,
      [command, startTimeOffsetSeconds, status, workerId]
    );
    return res.rows[0].job_id as string;
  });
}
