import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type MouseEvent } from "react";
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
  const router = useRouter();
  const [showLocations, setShowLocations] = useState(false);
  const others = job.other_locations ?? [];

  function toggleLocations(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setShowLocations((v) => !v);
  }

  // Buttons + router.push rather than <a>: the whole card is already a link,
  // and nested anchors are invalid HTML.
  function openSibling(e: MouseEvent, id: number) {
    e.preventDefault();
    e.stopPropagation();
    router.push(`/jobs/${id}`);
  }

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
        {(job.location || others.length > 0) && (
          <span>
            {job.location}
            {others.length > 0 && (
              <button
                onClick={toggleLocations}
                aria-expanded={showLocations}
                className="ml-1 font-medium text-blue-600 hover:underline"
              >
                +{others.length} location{others.length === 1 ? "" : "s"}
              </button>
            )}
          </span>
        )}
        {salary && <span>{salary}</span>}
        {job.source && <span className="capitalize">{job.source}</span>}
      </div>

      {showLocations && others.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2 text-xs">
          {others.map((o) => (
            <li key={o.id}>
              <button
                onClick={(e) => openSibling(e, o.id)}
                className="rounded-full border border-gray-200 px-2 py-0.5 text-gray-600 hover:border-blue-300 hover:text-blue-600"
              >
                {o.location || o.country?.toUpperCase() || "Unknown location"}
              </button>
            </li>
          ))}
        </ul>
      )}

      {job.match && (
        <MatchScoreBar score={job.match.match_score} size="sm" />
      )}
    </Link>
  );
}
