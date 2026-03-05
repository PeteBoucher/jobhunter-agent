"use client";

import { useSession } from "next-auth/react";
import { useState } from "react";
import useSWR from "swr";
import { createApplication, getApplications, getJob } from "@/lib/api";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { MatchScoreBar } from "@/components/MatchScoreBar";
import type { ApplicationStatus } from "@/lib/types";

export default function JobDetailPage({ params }: { params: { id: string } }) {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;
  const jobId = Number(params.id);

  const { data: job } = useSWR(
    token ? ["job", jobId] : null,
    () => getJob(token!, jobId)
  );

  const { data: applications, mutate: mutateApps } = useSWR(
    token ? ["applications"] : null,
    () => getApplications(token!)
  );

  const [applying, setApplying] = useState(false);
  const [toast, setToast] = useState("");

  const existingApp = applications?.find((a) => a.job_id === jobId);

  async function handleApply(status: ApplicationStatus) {
    if (!token) return;
    setApplying(true);
    try {
      await createApplication(token, jobId, status);
      await mutateApps();
      setToast(status === "saved" ? "Saved!" : "Marked as applied!");
      setTimeout(() => setToast(""), 3000);
    } catch {
      setToast("Something went wrong.");
    } finally {
      setApplying(false);
    }
  }

  if (!job) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-2 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
          <p className="text-gray-500">
            {job.company}
            {job.location && ` · ${job.location}`}
            {job.remote && ` · ${job.remote}`}
          </p>
        </div>
        {job.match && (
          <div className="w-32 shrink-0">
            <MatchScoreBar score={job.match.match_score} />
          </div>
        )}
      </div>

      {/* Salary */}
      {(job.salary_min || job.salary_max) && (
        <p className="mb-4 text-sm text-gray-500">
          {[job.salary_min && `€${job.salary_min.toLocaleString()}`, job.salary_max && `€${job.salary_max.toLocaleString()}`]
            .filter(Boolean)
            .join(" – ")}
          /yr
        </p>
      )}

      {/* Apply actions */}
      <div className="mb-6 flex flex-wrap gap-3">
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Apply externally →
          </a>
        )}
        {!existingApp && (
          <>
            <button
              onClick={() => handleApply("applied")}
              disabled={applying}
              className="rounded-lg border border-blue-600 px-4 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-50"
            >
              Mark as applied
            </button>
            <button
              onClick={() => handleApply("saved")}
              disabled={applying}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
            >
              Save for later
            </button>
          </>
        )}
        {existingApp && (
          <span className="inline-flex items-center rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-700">
            Status: {existingApp.status}
          </span>
        )}
        {toast && (
          <span className="inline-flex items-center text-sm text-green-600">{toast}</span>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {/* Description */}
          {job.description && (
            <section>
              <h2 className="mb-2 text-base font-semibold text-gray-800">Description</h2>
              <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm text-gray-600">
                {job.description}
              </div>
            </section>
          )}

          {/* Requirements */}
          {job.requirements && job.requirements.length > 0 && (
            <section>
              <h2 className="mb-2 text-base font-semibold text-gray-800">Requirements</h2>
              <ul className="list-disc space-y-1 pl-5 text-sm text-gray-600">
                {job.requirements.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </section>
          )}

          {/* Nice to haves */}
          {job.nice_to_haves && job.nice_to_haves.length > 0 && (
            <section>
              <h2 className="mb-2 text-base font-semibold text-gray-800">Nice to have</h2>
              <ul className="list-disc space-y-1 pl-5 text-sm text-gray-500">
                {job.nice_to_haves.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Score breakdown sidebar */}
        {job.match && (
          <div className="lg:col-span-1">
            <ScoreBreakdown match={job.match} />
          </div>
        )}
      </div>
    </div>
  );
}
