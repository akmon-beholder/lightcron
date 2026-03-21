import type { JobStatus } from "../../entities/job/model";

const ALL_STATUSES: Array<JobStatus | "all"> = [
  "all",
  "pending",
  "ready",
  "assigned",
  "running",
  "completed",
  "failed",
  "cancelled",
  "lost",
];

interface Props {
  value: JobStatus | "all";
  onChange: (value: JobStatus | "all") => void;
}

export function StatusFilter({ value, onChange }: Props) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 14, color: "#6b7280" }}>Status:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as JobStatus | "all")}
        style={{
          padding: "4px 8px",
          borderRadius: 6,
          border: "1px solid #d1d5db",
          fontSize: 14,
          background: "#fff",
        }}
      >
        {ALL_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
    </label>
  );
}
