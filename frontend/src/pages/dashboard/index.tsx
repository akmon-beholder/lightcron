import { useWorkers } from "../../shared/api/useWorkers";
import { DASHBOARD_REFRESH_INTERVAL_MS } from "../../shared/constants";
import { WorkerFleetPanel } from "../../widgets/worker-fleet-panel";
import { JobsPanel } from "../../widgets/jobs-panel";

export function DashboardPage() {
  const { data: workers, isLoading, isError } = useWorkers({
    refetchInterval: DASHBOARD_REFRESH_INTERVAL_MS,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <h1 style={{ margin: 0 }}>System Dashboard</h1>

      {isLoading && !workers && <p style={{ color: "#6b7280" }}>Loading workers…</p>}
      {isError && <p style={{ color: "#dc2626" }}>Failed to load workers.</p>}
      {workers !== undefined && <WorkerFleetPanel workers={workers} />}

      <JobsPanel />
    </div>
  );
}
