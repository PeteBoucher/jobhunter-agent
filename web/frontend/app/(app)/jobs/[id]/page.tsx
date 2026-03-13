"use client";

import DOMPurify from "dompurify";
import { useSession } from "next-auth/react";
import { useState } from "react";
import useSWR from "swr";
import { createApplication, getApplications, getJob } from "@/lib/api";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { MatchScoreBar } from "@/components/MatchScoreBar";
import type { ApplicationStatus } from "@/lib/types";

/** Detect whether a string contains HTML tags. */
function isHtml(text: string): boolean {
  return /<[a-z][\s\S]*>/i.test(text);
}

/** Render description safely — preserves HTML or converts plain-text newlines. */
function descriptionHtml(raw: string): string {
  let html: string;
  if (isHtml(raw)) {
    html = DOMPurify.sanitize(raw);
  } else {
    // Plain text: escape HTML entities, then wrap paragraphs
    const escaped = raw
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const body = escaped
      .replace(/\n{2,}/g, "</p><p>")
      .replace(/\n/g, "<br />");
    html = `<p>${body}</p>`;
  }

  // Promote short, unpunctuated <p> tags to <h3> headings.
  // Heuristic: ≤80 chars, ≤8 words, no trailing sentence punctuation, no <br>.
  return html.replace(/<p>([\s\S]*?)<\/p>/g, (match, inner) => {
    const text = inner.replace(/<[^>]+>/g, "").trim();
    const isHeading =
      text.length > 0 &&
      text.length <= 80 &&
      text.split(/\s+/).length <= 8 &&
      !/[.!?,;:)"']$/.test(text) &&
      !/<br/i.test(inner);
    return isHeading ? `<h3>${inner}</h3>` : match;
  });
}

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
    <div className="mx-auto max-w-5xl px-4 py-8">
      {/* Header */}
      <div className="mb-2 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            {job.company}
            {job.location && ` · ${job.location}`}
            {job.remote && ` · ${job.remote}`}
          </p>
        </div>
        {job.match && (
          <div className="w-28 shrink-0">
            <MatchScoreBar score={job.match.match_score} />
          </div>
        )}
      </div>

      {/* Salary */}
      {(job.salary_min || job.salary_max) && (
        <p className="mb-5 text-sm font-medium text-gray-600">
          {[
            job.salary_min && `€${job.salary_min.toLocaleString()}`,
            job.salary_max && `€${job.salary_max.toLocaleString()}`,
          ]
            .filter(Boolean)
            .join(" – ")}
          /yr
        </p>
      )}

      {/* Apply actions */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
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
          <span className="text-sm text-green-600">{toast}</span>
        )}
      </div>

      {/* Score breakdown — mobile: above description, desktop: sticky sidebar */}
      {job.match && (
        <div className="mb-6 lg:hidden">
          <ScoreBreakdown match={job.match} />
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-4">
        {/* Main content */}
        <div className="lg:col-span-3 space-y-8">
          {/* Description */}
          {job.description ? (
            <section>
              <h2 className="mb-3 text-base font-semibold text-gray-800">Description</h2>
              <div
                className="prose prose-gray max-w-none
                  [&_p]:my-4 [&_p]:leading-7 [&_p]:text-gray-600
                  [&_li]:my-2 [&_li]:leading-6 [&_li]:text-gray-600
                  [&_ul]:my-4 [&_ul]:pl-5 [&_ol]:my-4
                  [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-gray-800 [&_h2]:mt-6 [&_h2]:mb-2
                  [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-gray-800 [&_h3]:mt-4 [&_h3]:mb-1
                  [&_strong]:text-gray-800
                  [&_a]:text-blue-600 [&_a]:no-underline hover:[&_a]:underline"
                dangerouslySetInnerHTML={{
                  __html: descriptionHtml(job.description),
                }}
              />
            </section>
          ) : (
            <p className="text-sm italic text-gray-400">
              No description available for this listing.
            </p>
          )}

          {/* Requirements */}
          {job.requirements && job.requirements.length > 0 && (
            <section>
              <h2 className="mb-3 text-base font-semibold text-gray-800">Requirements</h2>
              <ul className="space-y-2 pl-0">
                {job.requirements.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-gray-600">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400" />
                    {r}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Nice to haves */}
          {job.nice_to_haves && job.nice_to_haves.length > 0 && (
            <section>
              <h2 className="mb-3 text-base font-semibold text-gray-800">Nice to have</h2>
              <ul className="space-y-2 pl-0">
                {job.nice_to_haves.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-gray-500">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-300" />
                    {r}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Score breakdown — desktop sticky sidebar */}
        {job.match && (
          <div className="hidden lg:block lg:col-span-1">
            <div className="sticky top-6">
              <ScoreBreakdown match={job.match} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
