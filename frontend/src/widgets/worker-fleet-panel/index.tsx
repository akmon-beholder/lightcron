import React from "react";
import type { Worker } from "../../entities/worker/model";
import { WorkerStatusBadge } from "../../entities/worker/WorkerStatusBadge";

function relativeTime(iso: string): string {
  const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  return `${Math.round(diff / 3600)}h ago`;
}

interface Props {
  workers: Worker[];
}

export function WorkerFleetPanel({ workers }: Props) {
  if (workers.length === 0) {
    return (
      <section>
        <h2 style={{ marginTop: 0 }}>Worker Fleet</h2>
        <p style={{ color: "#6b7280" }}>No workers registered</p>
      </section>
    );
  }

  return (
    <section>
      <h2 style={{ marginTop: 0 }}>Worker Fleet</h2>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ background: "#f3f4f6" }}>
            <th style={th}>Hostname</th>
            <th style={th}>Status</th>
            <th style={th}>Last Seen</th>
            <th style={th}>Running Jobs</th>
          </tr>
        </thead>
        <tbody>
          {workers.map((w) => (
            <tr
              key={w.worker_id}
              style={{ opacity: w.status === "offline" ? 0.6 : 1 }}
            >
              <td style={td}>{w.hostname}</td>
              <td style={td}>
                <WorkerStatusBadge status={w.status} />
              </td>
              <td style={td}>{relativeTime(w.last_seen)}</td>
              <td style={td}>{w.running_job_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
