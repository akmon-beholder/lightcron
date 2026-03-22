import { useQuery } from "@tanstack/react-query";
import type { Job, JobStatus } from "../../entities/job/model";
import apiClient from "./client";
import { JOB_DETAIL_REFRESH_INTERVAL_MS } from "../constants";

const TERMINAL_STATUSES: JobStatus[] = ["completed", "failed", "cancelled", "lost"];

export function isTerminalStatus(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

export function useJob(jobId: string) {
  return useQuery<Job>({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const { data } = await apiClient.get<Job>(`/jobs/${jobId}`);
      return data;
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && isTerminalStatus(data.status)) {
        return false;
      }
      return JOB_DETAIL_REFRESH_INTERVAL_MS;
    },
  });
}
