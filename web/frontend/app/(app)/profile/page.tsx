"use client";

import { useSession } from "next-auth/react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { getProfile, updateProfile } from "@/lib/api";

export default function ProfilePage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;

  const { data: user, mutate } = useSWR(
    token ? ["profile"] : null,
    () => getProfile(token!)
  );

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setName(user?.name ?? "");
    setTitle(user?.title ?? "");
    setLocation(user?.location ?? "");
    setEditing(true);
  }

  async function save() {
    if (!token) return;
    setSaving(true);
    try {
      await updateProfile(token, { name, title, location });
      await mutate();
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (!user) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Profile</h1>
        {!editing && (
          <button
            onClick={startEdit}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            Edit
          </button>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-4">
        {editing ? (
          <>
            <Field label="Name">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
              />
            </Field>
            <Field label="Current title">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
              />
            </Field>
            <Field label="Location">
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
              />
            </Field>
            <div className="flex gap-3 pt-2">
              <button
                onClick={save}
                disabled={saving}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => setEditing(false)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <Field label="Name">{user.name ?? "—"}</Field>
            <Field label="Current title">{user.title ?? "—"}</Field>
            <Field label="Location">{user.location ?? "—"}</Field>
            <Field label="Email">{user.email ?? "—"}</Field>
          </>
        )}
      </div>

      {/* Skills summary */}
      {user.skills.length > 0 && (
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">Skills ({user.skills.length})</h2>
          <div className="flex flex-wrap gap-2">
            {user.skills.slice(0, 30).map((s) => (
              <span
                key={s.id}
                className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs text-blue-700"
              >
                {s.skill_name}
              </span>
            ))}
            {user.skills.length > 30 && (
              <span className="text-xs text-gray-400">+{user.skills.length - 30} more</span>
            )}
          </div>
        </div>
      )}

      {/* Links */}
      <div className="mt-6 flex gap-4">
        <Link
          href="/profile/cv"
          className="flex-1 rounded-xl border border-gray-200 bg-white p-4 text-center text-sm font-medium text-gray-700 hover:border-blue-300 hover:bg-blue-50"
        >
          📄 Upload CV
        </Link>
        <Link
          href="/profile/preferences"
          className="flex-1 rounded-xl border border-gray-200 bg-white p-4 text-center text-sm font-medium text-gray-700 hover:border-blue-300 hover:bg-blue-50"
        >
          ⚙️ Job preferences
        </Link>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-gray-400 uppercase tracking-wide">{label}</p>
      <div className="text-sm text-gray-800">{children}</div>
    </div>
  );
}
