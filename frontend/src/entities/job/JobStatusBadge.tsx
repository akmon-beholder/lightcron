import type { JobStatus } from "./model";

const BADGE_STYLES: Record<JobStatus, string> = {
  pending: "background:#e5e7eb;color:#374151",
  ready: "background:#dbeafe;color:#1d4ed8",
  assigned: "background:#ede9fe;color:#6d28d9",
  running: "background:#fef3c7;color:#92400e",
  completed: "background:#d1fae5;color:#065f46",
  failed: "background:#fee2e2;color:#991b1b",
  cancelled: "background:#f3f4f6;color:#6b7280",
  lost: "background:#fff7ed;color:#c2410c",
};

interface Props {
  status: JobStatus;
}

export function JobStatusBadge({ status }: Props) {
  return (
    <span
      style={{
        ...parseStyle(BADGE_STYLES[status]),
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

function parseStyle(style: string): Record<string, string> {
  return Object.fromEntries(
    style.split(";").filter(Boolean).map((s) => {
      const [k, v] = s.split(":");
      return [k.trim(), v.trim()];
    })
  );
}
