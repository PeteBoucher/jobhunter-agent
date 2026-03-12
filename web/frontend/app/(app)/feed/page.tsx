"use client";

import { useSession } from "next-auth/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { getJobs, getProfile } from "@/lib/api";
import { JobCard } from "@/components/JobCard";

export default function FeedPage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;
  const searchParams = useSearchParams();
  const router = useRouter();
  const [bannerDismissed, setBannerDismissed] = useState(false);

  const { data: profile } = useSWR(
    token ? ["profile"] : null,
    () => getProfile(token!),
    { revalidateOnFocus: false }
  );
  const showCVBanner = !bannerDismissed && profile !== undefined && profile.skills.length === 0;

  // Read filter state from URL; fall back to sensible defaults
  const keywords = searchParams.get("keywords") ?? "";
  const remote = searchParams.get("remote") ?? "";
  const minScore = Number(searchParams.get("minScore") ?? 0);
  const sort = (searchParams.get("sort") ?? "score") as "score" | "date";
  const hideRejected = searchParams.get("hideRejected") !== "false";

  function setParam(key: string, value: string, defaultValue: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value === defaultValue) {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    router.replace(`/feed?${params.toString()}`);
  }

  const excludeStatuses = hideRejected ? ["rejected"] : [];

  const { data: jobs, isLoading, error } = useSWR(
    token ? ["jobs", keywords, remote, minScore, sort, hideRejected] : null,
    () =>
      getJobs(token!, {
        keywords: keywords || undefined,
        remote: remote || undefined,
        min_score: minScore > 0 ? minScore : undefined,
        sort,
        page_size: 50,
        exclude_statuses: excludeStatuses.length ? excludeStatuses : undefined,
      }),
    { revalidateOnFocus: false }
  );

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Job Feed</h1>

      {/* CV onboarding banner */}
      {showCVBanner && (
        <div className="mb-6 flex items-start gap-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <div className="flex-1">
            <p className="text-sm font-semibold text-blue-800">Upload your CV to unlock match scores</p>
            <p className="mt-1 text-sm text-blue-700">
              Without a CV every job shows the same score. Upload once and we&apos;ll re-score
              your entire feed against your skills automatically.
            </p>
            <Link
              href="/profile/cv"
              className="mt-3 inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Upload CV →
            </Link>
          </div>
          <button
            onClick={() => setBannerDismissed(true)}
            aria-label="Dismiss"
            className="shrink-0 text-blue-400 hover:text-blue-600 text-lg leading-none"
          >
            ×
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search keywords..."
          value={keywords}
          onChange={(e) => setParam("keywords", e.target.value, "")}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
        />
        <select
          value={remote}
          onChange={(e) => setParam("remote", e.target.value, "")}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
        >
          <option value="">Any location</option>
          <option value="remote">Remote</option>
          <option value="hybrid">Hybrid</option>
          <option value="onsite">Onsite</option>
        </select>
        <div className="flex items-center gap-2 text-sm">
          <label className="text-gray-500">Min score</label>
          <input
            type="range"
            min={0}
            max={90}
            step={10}
            value={minScore}
            onChange={(e) => setParam("minScore", e.target.value, "0")}
            className="w-24"
          />
          <span className="w-8 text-gray-700">{minScore > 0 ? `${minScore}%` : "—"}</span>
        </div>
        <div className="flex rounded-lg border border-gray-300 overflow-hidden text-sm">
          <button
            onClick={() => setParam("sort", "score", "score")}
            className={`px-3 py-2 ${sort === "score" ? "bg-blue-600 text-white" : "bg-white text-gray-600"}`}
          >
            Best match
          </button>
          <button
            onClick={() => setParam("sort", "date", "score")}
            className={`px-3 py-2 ${sort === "date" ? "bg-blue-600 text-white" : "bg-white text-gray-600"}`}
          >
            Newest
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={hideRejected}
            onChange={(e) =>
              setParam("hideRejected", String(e.target.checked), "true")
            }
            className="rounded"
          />
          Hide rejected
        </label>
      </div>

      {/* Job list */}
      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
        </div>
      )}
      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-600">
          Failed to load jobs. Make sure your profile is set up.
        </div>
      )}
      {jobs && jobs.length === 0 && (
        <p className="text-center text-gray-400 py-12">
          No jobs found — try adjusting your filters or{" "}
          <a href="/profile" className="text-blue-600 underline">
            upload your CV
          </a>
          .
        </p>
      )}
      {jobs && (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
