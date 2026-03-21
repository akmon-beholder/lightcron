export type JobStatus =
  | "pending"
  | "ready"
  | "assigned"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "lost";

export interface Job {
  job_id: string;
  command: string;
  start_time: string;
  depends_on: string[];
  max_runtime: number | null;
  max_memory: number | null;
  status: JobStatus;
  worker_id: string | null;
  exit_code: number | null;
  kill_reason: string | null;
  claimed_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}
