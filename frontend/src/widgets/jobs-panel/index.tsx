import React, { useState } from "react";
import { Link } from "react-router-dom";
import type { JobStatus } from "../../entities/job/model";
import type { Job } from "../../entities/job/model";
import { JobStatusBadge } from "../../entities/job/JobStatusBadge";
import { StatusFilter } from "../../features/filter-jobs/StatusFilter";
import { useJobs } from "../../shared/api/useJobs";
import { DASHBOARD_REFRESH_INTERVAL_MS } from "../../shared/constants";

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "…" : s;
}

export function JobsPanel() {
  const [statusFilter, setStatusFilter] = useState<JobStatus | "all">("all");
  const { data: jobs, isLoading, isError } = useJobs({
    status: statusFilter === "all" ? undefined : statusFilter,
    refetchInterval: DASHBOARD_REFRESH_INTERVAL_MS,
  });

  return (
    <section>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <h2 style={{ margin: 0 }}>Jobs</h2>
        <StatusFilter value={statusFilter} onChange={setStatusFilter} />
      </div>

      {isLoading && !jobs && <p style={{ color: "#6b7280" }}>Loading…</p>}
      {isError && (
        <p style={{ color: "#dc2626" }}>Failed to load jobs.</p>
      )}

      {jobs && jobs.length === 0 && (
        <p style={{ color: "#6b7280" }}>No jobs</p>
      )}

      {jobs && jobs.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f3f4f6" }}>
              <th style={th}>Job ID</th>
              <th style={th}>Command</th>
              <th style={th}>Status</th>
              <th style={th}>Worker</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j: Job) => (
              <tr
                key={j.job_id}
                style={{ cursor: "pointer" }}
                onClick={() => {
                  // navigation handled by the Link inside the row
                }}
              >
                <td style={{ ...td, fontFamily: "monospace", fontSize: 12, padding: 0 }}>
                  <Link
                    to={`/jobs/${j.job_id}`}
                    style={{
                      display: "block",
                      padding: "8px 12px",
                      color: "#1d4ed8",
                      textDecoration: "none",
                    }}
                  >
                    {j.job_id.slice(0, 8)}…
                  </Link>
                </td>
                <td style={td}>{truncate(j.command, 80)}</td>
                <td style={td}>
                  <JobStatusBadge status={j.status} />
                </td>
                <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>
                  {j.worker_id ? j.worker_id.slice(0, 8) + "…" : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  fontWeight: 600,
  borderBottom: "1px solid #e5e7eb",
};

const td: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #f3f4f6",
};
