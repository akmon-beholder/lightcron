import { useMutation } from "@tanstack/react-query";
import axios from "axios";
import type { Job } from "../../entities/job/model";
import apiClient from "../../shared/api/client";

export interface ScheduleJobInput {
  command: string;
  start_time: string;
  max_runtime?: number;
  max_memory?: number;
  depends_on?: string[];
}

export interface FieldError {
  field: string;
  msg: string;
}

export interface ScheduleJobError {
  fieldErrors: FieldError[];
  genericMessage: string | null;
}

export function useScheduleJob() {
  return useMutation<Job, ScheduleJobError, ScheduleJobInput>({
    mutationFn: async (input) => {
      const { data } = await apiClient.post<Job>("/jobs", input);
      return data;
    },
    onError: () => {
      // errors surfaced via mutation.error
    },
    throwOnError: false,
  });
}

export function parseScheduleJobError(err: unknown): ScheduleJobError {
  if (!axios.isAxiosError(err)) {
    return { fieldErrors: [], genericMessage: "An unexpected error occurred." };
  }

  const status = err.response?.status;
  const detail = err.response?.data?.detail;

  if (status === 422 && Array.isArray(detail)) {
    const fieldErrors: FieldError[] = detail.map(
      (d: { field?: string; loc?: string[]; msg?: string }) => ({
        field: d.field ?? (d.loc ? d.loc[d.loc.length - 1] : "unknown"),
        msg: d.msg ?? "Invalid value",
      })
    );
    return { fieldErrors, genericMessage: null };
  }

  const message =
    typeof detail === "string"
      ? detail
      : `Request failed with status ${status ?? "unknown"}.`;

  return { fieldErrors: [], genericMessage: message };
}
