export type WorkerStatus = "online" | "offline";

export interface Worker {
  worker_id: string;
  hostname: string;
  status: WorkerStatus;
  last_seen: string;
  registered_at: string;
  running_job_count: number;
}
