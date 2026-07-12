import type { Job } from "../types";

export default function JobBanner({ job, onRetry }: { job: Job | null; onRetry?: () => void }) {
  if (!job || job.status === "idle") return null;
  if (job.status === "done") return null;
  const failed = job.status === "failed";
  const pct = job.total > 0 ? Math.round((job.completed / job.total) * 100) : 0;

  return (
    <div className={`job-banner${failed ? " failed" : ""}`} role="status">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>
          {failed ? "Failed" : "Running"}: {job.name}
          {job.total > 0 && !failed && (
            <span className="muted"> — {job.completed}/{job.total}{job.current ? ` (${job.current})` : ""}</span>
          )}
        </span>
        {failed && onRetry && (
          <button className="ghost" style={{ padding: "4px 10px" }} onClick={onRetry}>
            retry
          </button>
        )}
      </div>
      {job.total > 0 && !failed && (
        <div style={{
          marginTop: 6, height: 4, borderRadius: 2,
          background: "var(--line)", overflow: "hidden",
        }}>
          <div style={{
            width: `${pct}%`, height: "100%",
            background: "var(--gold)", borderRadius: 2,
            transition: "width 0.3s ease",
          }} />
        </div>
      )}
      {job.log.length > 0 && <pre>{job.log.slice(-4).join("\n")}</pre>}
    </div>
  );
}
