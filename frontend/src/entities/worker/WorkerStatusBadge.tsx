import React from "react";
import type { WorkerStatus } from "./model";

const STYLES: Record<WorkerStatus, React.CSSProperties> = {
  online: { background: "#d1fae5", color: "#065f46" },
  offline: { background: "#e5e7eb", color: "#6b7280" },
};

interface Props {
  status: WorkerStatus;
}

export function WorkerStatusBadge({ status }: Props) {
  return (
    <span
      style={{
        ...STYLES[status],
        padding: "2px 8px",
        borderRadius: 9999,
        fontSize: 12,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      {status}
    </span>
  );
}
