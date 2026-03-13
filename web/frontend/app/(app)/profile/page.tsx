"use client";

import { signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { useRef, useState } from "react";
import useSWR from "swr";
import {
  deleteAccount,
  deleteSkill,
  getProfile,
  updateProfile,
  uploadCV,
} from "@/lib/api";

export default function ProfilePage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;

  const { data: user, mutate } = useSWR(
    token ? ["profile"] : null,
    () => getProfile(token!)
  );

  // Profile edit
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [saving, setSaving] = useState(false);

  // Account deletion
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Skills
  const [deletingSkillId, setDeletingSkillId] = useState<number | null>(null);

  // CV upload
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ skillCount: number } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  async function handleDeleteSkill(skillId: number) {
    if (!token) return;
    setDeletingSkillId(skillId);
    try {
      await deleteSkill(token, skillId);
      await mutate();
    } finally {
      setDeletingSkillId(null);
    }
  }

  async function handleDeleteAccount() {
    if (!token) return;
    setDeleting(true);
    try {
      await deleteAccount(token);
      await signOut({ callbackUrl: "/" });
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

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

  async function handleUpload(file: File) {
    if (!token) return;
    setUploading(true);
    setUploadResult(null);
    setUploadError(null);
    try {
      const updated = await uploadCV(token, file);
      setUploadResult({ skillCount: updated.skills.length });
      await mutate();
    } catch (err: any) {
      setUploadError(err.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
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

      {/* Profile fields */}
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

      {/* CV upload */}
      <div className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-gray-700">CV</h2>

        <div
          className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
            dragging
              ? "border-blue-400 bg-blue-50"
              : uploading
              ? "border-gray-200 bg-gray-50"
              : "cursor-pointer border-gray-300 bg-white hover:border-blue-300 hover:bg-blue-50/40"
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
              e.target.value = "";
            }}
          />

          {uploading ? (
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" />
              <p className="text-sm font-medium text-gray-700">Analysing your CV…</p>
              <p className="text-xs text-gray-400">This usually takes 5–10 seconds</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <svg
                className="h-8 w-8 text-gray-400"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.338-2.32 5.75 5.75 0 0 1 .087 11.096"
                />
              </svg>
              <p className="text-sm font-medium text-gray-700">
                {dragging ? "Drop to upload" : "Drop your CV here, or click to browse"}
              </p>
              <p className="text-xs text-gray-400">PDF, DOCX, TXT or Markdown · max 5 MB</p>
            </div>
          )}
        </div>

        {uploadResult && (
          <div className="mt-3 flex items-start gap-3 rounded-lg bg-green-50 p-4">
            <svg
              className="mt-0.5 h-4 w-4 shrink-0 text-green-600"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
            <div className="min-w-0">
              <p className="text-sm font-medium text-green-800">
                CV uploaded — {uploadResult.skillCount} skills extracted
              </p>
              <p className="mt-0.5 flex items-center gap-1.5 text-xs text-green-700">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
                Rescoring your job matches in the background
              </p>
            </div>
          </div>
        )}

        {uploadError && (
          <div className="mt-3 rounded-lg bg-red-50 p-4 text-sm text-red-600">
            {uploadError}
          </div>
        )}
      </div>

      {/* Skills */}
      {user.skills.length > 0 && (
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">
            Skills ({user.skills.length})
          </h2>
          <div className="flex flex-wrap gap-2">
            {user.skills.map((s) => (
              <span
                key={s.id}
                className="group flex items-center gap-1 rounded-full bg-blue-50 pl-2.5 pr-1.5 py-0.5 text-xs text-blue-700"
              >
                {s.skill_name}
                <button
                  onClick={() => handleDeleteSkill(s.id)}
                  disabled={deletingSkillId === s.id}
                  className="ml-0.5 rounded-full p-0.5 text-blue-400 hover:bg-blue-200 hover:text-blue-700 disabled:opacity-40"
                  aria-label={`Remove ${s.skill_name}`}
                >
                  {deletingSkillId === s.id ? "…" : "×"}
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Job preferences link */}
      <div className="mt-6">
        <Link
          href="/profile/preferences"
          className="flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-sm font-medium text-gray-700 hover:border-blue-300 hover:bg-blue-50"
        >
          <span>⚙️ Job preferences</span>
          <svg
            className="h-4 w-4 text-gray-400"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
          </svg>
        </Link>
      </div>

      {/* Danger zone */}
      <div className="mt-10 rounded-xl border border-red-200 bg-red-50 p-6">
        <h2 className="mb-1 text-sm font-semibold text-red-700">Danger zone</h2>
        <p className="mb-4 text-xs text-red-600">
          Permanently deletes your account, CV, skills, preferences, and application
          history. This cannot be undone.
        </p>
        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            className="rounded-lg border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100"
          >
            Delete my account
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-red-700">Are you sure?</span>
            <button
              onClick={handleDeleteAccount}
              disabled={deleting}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
            >
              {deleting ? "Deleting…" : "Yes, delete everything"}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
        )}
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
