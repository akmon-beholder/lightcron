import { useQuery } from "@tanstack/react-query";

interface UseJobOutputParams {
  baseUrl: string | null;
  jobId: string;
  stream: "stdout" | "stderr";
  enabled: boolean;
}

interface JobOutputResult {
  data: string | null;
  isOffline: boolean;
  isLoading: boolean;
}

export function useJobOutput({
  baseUrl,
  jobId,
  stream,
  enabled,
}: UseJobOutputParams): JobOutputResult {
  const isEnabled = enabled && baseUrl !== null;

  const query = useQuery<string | null, Error>({
    queryKey: ["job-output", baseUrl, jobId, stream],
    queryFn: async () => {
      const url = `${baseUrl}/jobs/${jobId}/${stream}`;
      const response = await fetch(url);
      if (response.status === 404) {
        return null;
      }
      if (!response.ok) {
        throw new Error(`Unexpected status ${response.status}`);
      }
      return response.text();
    },
    enabled: isEnabled,
    // Terminal jobs have stable output — no auto-refresh
    refetchInterval: false,
    retry: false,
  });

  if (!isEnabled) {
    return { data: null, isOffline: false, isLoading: false };
  }

  if (query.isLoading) {
    return { data: null, isOffline: false, isLoading: true };
  }

  if (query.isError) {
    return { data: null, isOffline: true, isLoading: false };
  }

  return {
    data: query.data ?? null,
    isOffline: false,
    isLoading: false,
  };
}
