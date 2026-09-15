import Link from "next/link";
import type { MouseEvent } from "react";
import type { Job } from "@/lib/types";
import { MatchScoreBar } from "./MatchScoreBar";

interface Props {
  job: Job;
  /** When provided, shows a "Not interested" button that calls back with an
   * optional reason instead of navigating to the job. */
  onReject?: (jobId: number, reason?: string) => void;
}

const remoteBadge: Record<string, string> = {
  remote: "bg-green-100 text-green-700",
  hybrid: "bg-amber-100 text-amber-700",
  onsite: "bg-gray-100 text-gray-600",
};

function formatSalary(min: number | null, max: number | null): string {
  if (!min && !max) return "";
  const fmt = (n: number) =>
    n >= 1000 ? `€${(n / 1000).toFixed(0)}k` : `€${n}`;
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  if (min) return `from ${fmt(min)}`;
  return `up to ${fmt(max!)}`;
}

export function JobCard({ job, onReject }: Props) {
  const salary = formatSalary(job.salary_min, job.salary_max);
  const remoteKey = job.remote?.toLowerCase() ?? "";

  function handleReject(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!onReject) return;
    const reason = window.prompt(
      "Optional: why isn't this job for you? (leave blank to skip)"
    );
    if (reason === null) return; // cancelled
    onReject(job.id, reason.trim() || undefined);
  }

  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block rounded-xl border border-gray-200 bg-white p-5 shadow-sm hover:border-blue-300 hover:shadow-md transition-all"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate font-semibold text-gray-900">{job.title}</h2>
          <p className="truncate text-sm text-gray-500">{job.company}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {remoteKey && remoteBadge[remoteKey] && (
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${remoteBadge[remoteKey]}`}
            >
              {job.remote}
            </span>
          )}
          {onReject && (
            <button
              onClick={handleReject}
              aria-label="Not interested"
              title="Not interested"
              className="rounded-full p-1 text-gray-300 hover:bg-red-50 hover:text-red-500 transition-colors"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        {job.location && <span>{job.location}</span>}
        {salary && <span>{salary}</span>}
        {job.source && <span className="capitalize">{job.source}</span>}
      </div>

      {job.match && (
        <MatchScoreBar score={job.match.match_score} size="sm" />
      )}
    </Link>
  );
}
