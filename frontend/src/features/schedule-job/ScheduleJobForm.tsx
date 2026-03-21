import React, { useState } from "react";
import {
  parseScheduleJobError,
  useScheduleJob,
  type FieldError,
} from "./useScheduleJob";

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  fontSize: 14,
  marginTop: 4,
};

const errorStyle: React.CSSProperties = {
  color: "#dc2626",
  fontSize: 13,
  marginTop: 2,
};

interface FieldState {
  command: string;
  start_time: string;
  max_runtime: string;
  max_memory: string;
  depends_on: string;
}

export function ScheduleJobForm() {
  const mutation = useScheduleJob();
  const [fields, setFields] = useState<FieldState>({
    command: "",
    start_time: "",
    max_runtime: "",
    max_memory: "",
    depends_on: "",
  });
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});

  function set(key: keyof FieldState, value: string) {
    setFields((f) => ({ ...f, [key]: value }));
    setClientErrors((e) => ({ ...e, [key]: "" }));
  }

  function validate(): boolean {
    const errors: Record<string, string> = {};
    if (!fields.command.trim()) errors.command = "Command is required.";
    if (!fields.start_time) {
      errors.start_time = "Start time is required.";
    } else if (new Date(fields.start_time) <= new Date()) {
      errors.start_time = "Start time must be in the future.";
    }
    if (fields.max_runtime && Number(fields.max_runtime) <= 0)
      errors.max_runtime = "Max runtime must be greater than 0.";
    if (fields.max_memory && Number(fields.max_memory) <= 0)
      errors.max_memory = "Max memory must be greater than 0.";
    setClientErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    const depends_on = fields.depends_on
      ? fields.depends_on
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : undefined;

    await mutation.mutateAsync({
      command: fields.command.trim(),
      start_time: new Date(fields.start_time).toISOString(),
      ...(fields.max_runtime ? { max_runtime: Number(fields.max_runtime) } : {}),
      ...(fields.max_memory ? { max_memory: Number(fields.max_memory) } : {}),
      ...(depends_on?.length ? { depends_on } : {}),
    });
  }

  const serverError = mutation.error
    ? parseScheduleJobError(mutation.error)
    : null;

  function serverFieldError(field: string): string | undefined {
    return serverError?.fieldErrors.find((e: FieldError) => e.field === field)
      ?.msg;
  }

  const fieldError = (key: string) =>
    clientErrors[key] ?? serverFieldError(key);

  return (
    <form onSubmit={(e) => void handleSubmit(e)} noValidate style={{ maxWidth: 480 }}>
      {serverError?.genericMessage && (
        <p
          style={{
            color: "#dc2626",
            background: "#fee2e2",
            padding: "8px 12px",
            borderRadius: 6,
            marginBottom: 16,
          }}
        >
          {serverError.genericMessage}
        </p>
      )}

      <div style={{ marginBottom: 16 }}>
        <label>
          <span style={{ fontWeight: 600 }}>Command *</span>
          <input
            style={inputStyle}
            type="text"
            value={fields.command}
            onChange={(e) => set("command", e.target.value)}
            placeholder="/usr/bin/my-script.sh"
          />
        </label>
        {fieldError("command") && (
          <p style={errorStyle}>{fieldError("command")}</p>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        <label>
          <span style={{ fontWeight: 600 }}>Start Time *</span>
          <input
            style={inputStyle}
            type="datetime-local"
            value={fields.start_time}
            onChange={(e) => set("start_time", e.target.value)}
          />
        </label>
        {fieldError("start_time") && (
          <p style={errorStyle}>{fieldError("start_time")}</p>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        <label>
          <span style={{ fontWeight: 600 }}>Max Runtime (seconds)</span>
          <input
            style={inputStyle}
            type="number"
            min={1}
            value={fields.max_runtime}
            onChange={(e) => set("max_runtime", e.target.value)}
            placeholder="Optional"
          />
        </label>
        {fieldError("max_runtime") && (
          <p style={errorStyle}>{fieldError("max_runtime")}</p>
        )}
      </div>

      <div style={{ marginBottom: 16 }}>
        <label>
          <span style={{ fontWeight: 600 }}>Max Memory (MB)</span>
          <input
            style={inputStyle}
            type="number"
            min={1}
            value={fields.max_memory}
            onChange={(e) => set("max_memory", e.target.value)}
            placeholder="Optional"
          />
        </label>
        {fieldError("max_memory") && (
          <p style={errorStyle}>{fieldError("max_memory")}</p>
        )}
      </div>

      <div style={{ marginBottom: 24 }}>
        <label>
          <span style={{ fontWeight: 600 }}>Depends On (comma-separated UUIDs)</span>
          <input
            style={inputStyle}
            type="text"
            value={fields.depends_on}
            onChange={(e) => set("depends_on", e.target.value)}
            placeholder="Optional — e.g. uuid1, uuid2"
          />
        </label>
        {fieldError("depends_on") && (
          <p style={errorStyle}>{fieldError("depends_on")}</p>
        )}
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        style={{
          padding: "8px 20px",
          background: "#2563eb",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          fontWeight: 600,
          cursor: mutation.isPending ? "not-allowed" : "pointer",
          opacity: mutation.isPending ? 0.7 : 1,
        }}
      >
        {mutation.isPending ? "Submitting…" : "Schedule Job"}
      </button>

      {mutation.isSuccess && mutation.data && (
        <div
          style={{
            marginTop: 24,
            padding: "12px 16px",
            background: "#d1fae5",
            borderRadius: 6,
          }}
        >
          <p style={{ margin: 0, fontWeight: 600, color: "#065f46" }}>
            Job scheduled successfully!
          </p>
          <p style={{ margin: "4px 0 0", fontSize: 13, wordBreak: "break-all" }}>
            Job ID: <code>{mutation.data.job_id}</code>
          </p>
          <a
            href={`/jobs/${mutation.data.job_id}`}
            style={{ fontSize: 13, color: "#2563eb" }}
          >
            View job detail →
          </a>
        </div>
      )}
    </form>
  );
}
