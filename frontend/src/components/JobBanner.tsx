import type { Job } from "../types";

export default function JobBanner({ job, onRetry }: { job: Job | null; onRetry?: () => void }) {
  if (!job || job.status === "idle") return null;
  if (job.status === "done") return null;
  const failed = job.status === "failed";
  return (
    <div className={`job-banner${failed ? " failed" : ""}`} role="status">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <span>{failed ? "Job failed" : "Running"}: {job.name}</span>
        {failed && onRetry && (
          <button className="ghost" style={{ padding: "4px 10px" }} onClick={onRetry}>
            retry
          </button>
        )}
      </div>
      {job.log.length > 0 && <pre>{job.log.slice(-6).join("\n")}</pre>}
    </div>
  );
}
