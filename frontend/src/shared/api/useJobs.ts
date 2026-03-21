import { useQuery } from "@tanstack/react-query";
import type { Job } from "../../entities/job/model";
import apiClient from "./client";

export function useJobs(options?: { status?: string; refetchInterval?: number }) {
  const params = options?.status ? { status: options.status } : undefined;

  return useQuery<Job[]>({
    queryKey: ["jobs", options?.status ?? "all"],
    queryFn: async () => {
      const { data } = await apiClient.get<Job[]>("/jobs", { params });
      return data;
    },
    refetchInterval: options?.refetchInterval,
  });
}
