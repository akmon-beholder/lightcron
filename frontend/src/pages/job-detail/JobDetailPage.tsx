import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useJob, isTerminalStatus } from "../../shared/api/useJob";
import { useWorkers } from "../../shared/api/useWorkers";
import { useJobOutput } from "../../shared/api/useJobOutput";
import { JobStatusBadge } from "../../entities/job/JobStatusBadge";
import type { JobStatus } from "../../entities/job/model";

// ── Formatting helpers ─────────────────────────────────────────────────────

function formatRuntime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function elapsedSeconds(startedAt: string): number {
  return Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
}

function formatDateOrDash(val: string | null | undefined): string {
  if (!val) return "—";
  return new Date(val).toLocaleString();
}

// ── Live elapsed timer ─────────────────────────────────────────────────────

function LiveElapsed({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState<number>(elapsedSeconds(startedAt));

  useEffect(() => {
    const id = setInterval(() => {
      setElapsed(elapsedSeconds(startedAt));
    }, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  return <span data-testid="live-elapsed">{formatRuntime(elapsed)}</span>;
}

// ── Output block ───────────────────────────────────────────────────────────

interface OutputBlockProps {
  label: string;
  content: string | null;
  isOffline: boolean;
  isLoading: boolean;
  isTerminal: boolean;
  hasBaseUrl: boolean;
  isStderr?: boolean;
}

function OutputBlock({
  label,
  content,
  isOffline,
  isLoading,
  isTerminal,
  hasBaseUrl,
  isStderr = false,
}: OutputBlockProps) {
  const labelColor = isStderr ? "#b91c1c" : "#1d4ed8";
  const borderColor = isStderr ? "#fca5a5" : "#bfdbfe";

  return (
    <div
      style={{
        border: `1px solid ${borderColor}`,
        borderRadius: 6,
        overflow: "hidden",
        flex: 1,
        minWidth: 0,
      }}
    >
      <div
        style={{
          background: isStderr ? "#fee2e2" : "#eff6ff",
          padding: "6px 12px",
          fontWeight: 600,
          fontSize: 13,
          color: labelColor,
        }}
      >
        {label}
      </div>
      <div style={{ padding: 12 }}>
        {!isTerminal ? (
          <p
            style={{ color: "#6b7280", fontStyle: "italic", margin: 0 }}
            data-testid={isStderr ? "stderr-in-progress" : "stdout-in-progress"}
          >
            Job in progress — output will appear here once the job completes
          </p>
        ) : !hasBaseUrl || isOffline ? (
          <p
            style={{ color: "#dc2626", margin: 0 }}
            data-testid={isStderr ? "stderr-offline" : "stdout-offline"}
          >
            Worker offline — logs unavailable
          </p>
        ) : isLoading ? (
          <p style={{ color: "#6b7280", margin: 0 }}>Loading…</p>
        ) : content === null ? (
          <p
            style={{ color: "#6b7280", fontStyle: "italic", margin: 0 }}
            data-testid={isStderr ? "stderr-no-output" : "stdout-no-output"}
          >
            No output
          </p>
        ) : (
          <pre
            style={{
              margin: 0,
              maxHeight: 400,
              overflowY: "auto",
              fontSize: 12,
              fontFamily: "monospace",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
            data-testid={isStderr ? "stderr-content" : "stdout-content"}
          >
            {content}
          </pre>
        )}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export function JobDetailPage() {
  const { job_id: jobId } = useParams<{ job_id: string }>();

  const {
    data: job,
    isLoading,
    isError,
    error,
    refetch,
  } = useJob(jobId ?? "");

  const { data: workers } = useWorkers();

  const isTerminal = job ? isTerminalStatus(job.status) : false;

  // Resolve worker base_url from the workers list
  const workerBaseUrl =
    job && workers
      ? (workers.find((w) => w.worker_id === job.worker_id)?.base_url ?? null)
      : null;

  const stdoutOutput = useJobOutput({
    baseUrl: workerBaseUrl,
    jobId: jobId ?? "",
    stream: "stdout",
    enabled: isTerminal,
  });

  const stderrOutput = useJobOutput({
    baseUrl: workerBaseUrl,
    jobId: jobId ?? "",
    stream: "stderr",
    enabled: isTerminal,
  });

  // ── Error/loading states ─────────────────────────────────────────────────

  if (!jobId) {
    return (
      <div>
        <p style={{ color: "#dc2626" }}>Invalid job URL.</p>
        <Link to="/">← Back to dashboard</Link>
      </div>
    );
  }

  if (isLoading) {
    return <p style={{ color: "#6b7280" }}>Loading job…</p>;
  }

  if (isError) {
    // Axios 404 → error.response.status === 404
    const axiosError = error as { response?: { status?: number } } | null;
    const is404 = axiosError?.response?.status === 404;

    if (is404) {
      return (
        <div data-testid="job-not-found">
          <h2 style={{ color: "#dc2626" }}>Job not found</h2>
          <p>The job "{jobId}" does not exist.</p>
          <Link to="/" data-testid="dashboard-link">
            ← Back to dashboard
          </Link>
        </div>
      );
    }

    return (
      <div>
        <p style={{ color: "#dc2626" }}>Could not load job. Please try again.</p>
        <button onClick={() => void refetch()} style={{ marginRight: 12 }}>
          Retry
        </button>
        <Link to="/">← Back to dashboard</Link>
      </div>
    );
  }

  if (!job) {
    return null;
  }

  // ── Runtime computation ─────────────────────────────────────────────────

  const isRunning = (job.status as JobStatus) === "running";

  let runtimeDisplay: React.ReactNode = "—";
  if (job.started_at && job.finished_at) {
    const diffSeconds = Math.floor(
      (new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000
    );
    runtimeDisplay = formatRuntime(diffSeconds);
  } else if (job.started_at && isRunning) {
    runtimeDisplay = <LiveElapsed startedAt={job.started_at} />;
  }

  // ── Peak memory ─────────────────────────────────────────────────────────

  let peakMemoryDisplay: React.ReactNode;
  if (job.peak_memory_mb !== null && job.peak_memory_mb !== undefined) {
    peakMemoryDisplay = `${job.peak_memory_mb} MB`;
  } else if (isRunning || job.status === "assigned") {
    peakMemoryDisplay = (
      <span
        style={{ color: "#6b7280", fontStyle: "italic" }}
        data-testid="peak-memory-in-progress"
      >
        job in progress
      </span>
    );
  } else {
    peakMemoryDisplay = (
      <span
        style={{ color: "#6b7280", fontStyle: "italic" }}
        data-testid="peak-memory-placeholder"
      >
        not yet available
      </span>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Back link */}
      <div>
        <Link to="/" style={{ color: "#1d4ed8", textDecoration: "none" }}>
          ← Back to dashboard
        </Link>
      </div>

      {/* Section 1: Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <code
          style={{ fontSize: 18, fontFamily: "monospace", wordBreak: "break-all" }}
          data-testid="job-id"
        >
          {job.job_id}
        </code>
        <JobStatusBadge status={job.status} />
        {!isTerminal && (
          <span
            style={{
              marginLeft: "auto",
              background: "#fee2e2",
              color: "#991b1b",
              padding: "4px 12px",
              borderRadius: 4,
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            Cancel
          </span>
        )}
      </div>

      {/* Section 2: Summary */}
      <section>
        <h2 style={{ marginBottom: 12, fontSize: 16 }}>Summary</h2>
        <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
          <tbody>
            <SummaryRow label="Command">
              <code style={{ fontFamily: "monospace" }}>{job.command}</code>
            </SummaryRow>
            <SummaryRow label="Worker">{job.worker_id ?? "—"}</SummaryRow>
            <SummaryRow label="Created">{formatDateOrDash(job.created_at)}</SummaryRow>
            <SummaryRow label="Claimed">{formatDateOrDash(job.claimed_at)}</SummaryRow>
            <SummaryRow label="Started">{formatDateOrDash(job.started_at)}</SummaryRow>
            <SummaryRow label="Finished">{formatDateOrDash(job.finished_at)}</SummaryRow>
          </tbody>
        </table>
      </section>

      {/* Section 3: Runtime and Resources */}
      <section>
        <h2 style={{ marginBottom: 12, fontSize: 16 }}>Runtime &amp; Resources</h2>

        {/* Kill reason banner */}
        {job.kill_reason && (
          <div
            style={{
              background: "#fef3c7",
              border: "1px solid #fbbf24",
              borderRadius: 6,
              padding: "10px 16px",
              marginBottom: 12,
              color: "#92400e",
              fontWeight: 600,
            }}
            data-testid="kill-reason-banner"
          >
            ⚠ Kill reason: {job.kill_reason}
          </div>
        )}

        <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
          <tbody>
            <SummaryRow label="Actual runtime">{runtimeDisplay}</SummaryRow>
            <SummaryRow label="Peak memory">{peakMemoryDisplay}</SummaryRow>
            <SummaryRow label="Max runtime">
              {job.max_runtime != null ? `${job.max_runtime}s` : "Unlimited"}
            </SummaryRow>
            <SummaryRow label="Max memory">
              {job.max_memory != null ? `${job.max_memory} MB` : "Unlimited"}
            </SummaryRow>
          </tbody>
        </table>
      </section>

      {/* Section 4: Environment Variables */}
      <section>
        <h2 style={{ marginBottom: 12, fontSize: 16 }}>Environment Variables</h2>
        {Object.keys(job.env_vars).length === 0 ? (
          <p
            style={{ color: "#6b7280", fontStyle: "italic" }}
            data-testid="no-env-vars"
          >
            No environment variables
          </p>
        ) : (
          <table
            style={{ borderCollapse: "collapse", fontSize: 14, width: "100%" }}
            data-testid="env-vars-table"
          >
            <thead>
              <tr style={{ background: "#f3f4f6" }}>
                <th style={thStyle}>Key</th>
                <th style={thStyle}>Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(job.env_vars).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ ...tdStyle, fontFamily: "monospace" }}>{k}</td>
                  <td style={{ ...tdStyle, fontFamily: "monospace" }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Section 5: Output */}
      <section>
        <h2 style={{ marginBottom: 12, fontSize: 16 }}>Output</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          <OutputBlock
            label="stdout"
            content={stdoutOutput.data}
            isOffline={stdoutOutput.isOffline}
            isLoading={stdoutOutput.isLoading}
            isTerminal={isTerminal}
            hasBaseUrl={workerBaseUrl !== null}
          />
          <OutputBlock
            label="stderr"
            content={stderrOutput.data}
            isOffline={stderrOutput.isOffline}
            isLoading={stderrOutput.isLoading}
            isTerminal={isTerminal}
            hasBaseUrl={workerBaseUrl !== null}
            isStderr
          />
        </div>
      </section>

      {/* Section 6: Dependencies */}
      <section>
        <h2 style={{ marginBottom: 12, fontSize: 16 }}>Dependencies</h2>
        {job.depends_on.length === 0 ? (
          <p style={{ color: "#6b7280", fontStyle: "italic" }}>No dependencies</p>
        ) : (
          <ul style={{ paddingLeft: 20, fontSize: 14 }}>
            {job.depends_on.map((dep) => (
              <li key={dep}>
                <Link to={`/jobs/${dep}`} style={{ fontFamily: "monospace" }}>
                  {dep}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// ── Small helpers ──────────────────────────────────────────────────────────

function SummaryRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <tr>
      <td
        style={{
          padding: "6px 24px 6px 0",
          color: "#6b7280",
          fontWeight: 600,
          whiteSpace: "nowrap",
          verticalAlign: "top",
        }}
      >
        {label}
      </td>
      <td style={{ padding: "6px 0", verticalAlign: "top" }}>{children}</td>
    </tr>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "6px 12px",
  fontWeight: 600,
  borderBottom: "1px solid #e5e7eb",
};

const tdStyle: React.CSSProperties = {
  padding: "6px 12px",
  borderBottom: "1px solid #f3f4f6",
};
