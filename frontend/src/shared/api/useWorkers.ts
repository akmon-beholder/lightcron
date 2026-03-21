import { useQuery } from "@tanstack/react-query";
import type { Worker } from "../../entities/worker/model";
import apiClient from "./client";

export function useWorkers(options?: { refetchInterval?: number }) {
  return useQuery<Worker[]>({
    queryKey: ["workers"],
    queryFn: async () => {
      const { data } = await apiClient.get<Worker[]>("/workers");
      return data;
    },
    refetchInterval: options?.refetchInterval,
  });
}
