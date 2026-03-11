"use client";

import { useSession } from "next-auth/react";
import useSWR from "swr";
import { getApplications, updateApplication } from "@/lib/api";
import type { Application, ApplicationStatus } from "@/lib/types";

const COLUMNS: { status: ApplicationStatus; label: string; colour: string }[] = [
  { status: "saved", label: "Saved", colour: "bg-gray-100" },
  { status: "applied", label: "Applied", colour: "bg-blue-100" },
  { status: "interview_scheduled", label: "Interview", colour: "bg-amber-100" },
  { status: "offer", label: "Offer", colour: "bg-green-100" },
  { status: "rejected", label: "Rejected", colour: "bg-red-100" },
];

function AppCard({ app }: { app: Application }) {
  return (
    <a href={`/jobs/${app.job_id}`} className="block rounded-lg border border-gray-200 bg-white p-3 shadow-sm hover:border-blue-300 hover:shadow-md transition-shadow">
      <p className="text-sm font-medium text-gray-800 line-clamp-2">
        {app.job_title ?? `Job #${app.job_id}`}
      </p>
      {app.job_company && (
        <p className="mt-0.5 text-xs text-gray-500">{app.job_company}</p>
      )}
      {app.notes && (
        <p className="mt-1 text-xs text-gray-400 line-clamp-2">{app.notes}</p>
      )}
      {app.application_date && (
        <p className="mt-1 text-xs text-gray-300">
          {new Date(app.application_date).toLocaleDateString()}
        </p>
      )}
    </a>
  );
}

export default function ApplicationsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;

  const { data: applications, mutate } = useSWR(
    token ? ["applications"] : null,
    () => getApplications(token!)
  );

  async function moveApp(app: Application, newStatus: ApplicationStatus) {
    if (!token) return;
    try {
      await updateApplication(token, app.id, newStatus);
      await mutate();
    } catch {
      // no-op
    }
  }

  const byStatus = (status: ApplicationStatus) =>
    (applications ?? []).filter((a) => a.status === status);

  const total = applications?.length ?? 0;
  const interviews = byStatus("interview_scheduled").length;
  const offers = byStatus("offer").length;

  return (
    <div className="px-4 py-8 pb-24 md:pb-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Applications</h1>
        <div className="flex gap-4 text-sm text-gray-500">
          <span>{total} total</span>
          <span>{interviews} interviews</span>
          <span>{offers} offers</span>
        </div>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map((col) => {
          const apps = byStatus(col.status);
          return (
            <div
              key={col.status}
              className="flex w-60 shrink-0 flex-col"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                const id = Number(e.dataTransfer.getData("application_id"));
                const app = applications?.find((a) => a.id === id);
                if (app && app.status !== col.status) {
                  moveApp(app, col.status);
                }
              }}
            >
              <div className={`mb-3 rounded-lg px-3 py-2 ${col.colour}`}>
                <span className="text-sm font-semibold text-gray-700">{col.label}</span>
                <span className="ml-2 text-xs text-gray-400">{apps.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {apps.map((app) => (
                  <div
                    key={app.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData("application_id", String(app.id));
                    }}
                    className="cursor-grab active:cursor-grabbing"
                  >
                    <AppCard app={app} />
                  </div>
                ))}
                {apps.length === 0 && (
                  <p className="text-center text-xs text-gray-300 py-4">Empty</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-4 text-xs text-gray-400">
        Drag cards between columns to update status.
      </p>
    </div>
  );
}
