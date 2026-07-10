import type { Job } from "../types";

export default function JobBanner({ job }: { job: Job | null }) {
  if (!job || job.status === "idle") return null;
  if (job.status === "done") return null;
  const failed = job.status === "failed";
  return (
    <div className={`job-banner${failed ? " failed" : ""}`} role="status">
      {failed ? "Job failed" : "Running"}: {job.name}
      {job.log.length > 0 && <pre>{job.log.slice(-4).join("\n")}</pre>}
    </div>
  );
}
