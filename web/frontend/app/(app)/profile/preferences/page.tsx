"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { getPreferences, updatePreferences } from "@/lib/api";
import type { Preferences } from "@/lib/types";

function TagInput({
  values,
  onChange,
  placeholder,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");

  function add() {
    const v = input.trim();
    if (v && !values.includes(v)) {
      onChange([...values, v]);
    }
    setInput("");
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {values.map((v) => (
          <span
            key={v}
            className="flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs text-blue-700"
          >
            {v}
            <button onClick={() => onChange(values.filter((x) => x !== v))} className="text-blue-400 hover:text-blue-700">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder={placeholder}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-400 focus:outline-none"
        />
        <button onClick={add} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50">
          Add
        </button>
      </div>
    </div>
  );
}

export default function PreferencesPage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;

  const { data: prefs, mutate } = useSWR(
    token ? ["preferences"] : null,
    () => getPreferences(token!)
  );

  const [form, setForm] = useState<Partial<Preferences>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (prefs) setForm(prefs);
  }, [prefs]);

  function set<K extends keyof Preferences>(key: K, val: Preferences[K]) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function save() {
    if (!token) return;
    setSaving(true);
    try {
      await updatePreferences(token, form);
      await mutate();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Job Preferences</h1>

      <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-6">
        <Section label="Target job titles">
          <TagInput
            values={form.target_titles ?? []}
            onChange={(v) => set("target_titles", v)}
            placeholder="e.g. Senior Engineer"
          />
        </Section>

        <Section label="Preferred locations">
          <TagInput
            values={form.preferred_locations ?? []}
            onChange={(v) => set("preferred_locations", v)}
            placeholder="e.g. Barcelona"
          />
        </Section>

        <Section label="Remote preference">
          <div className="flex gap-3">
            {["remote", "hybrid", "onsite"].map((r) => (
              <label key={r} className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="remote"
                  value={r}
                  checked={form.remote_preference === r}
                  onChange={() => set("remote_preference", r)}
                />
                <span className="capitalize">{r}</span>
              </label>
            ))}
          </div>
        </Section>

        <Section label="Experience level">
          <select
            value={form.experience_level ?? ""}
            onChange={(e) => set("experience_level", e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
          >
            <option value="">— select —</option>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
            <option value="lead">Lead</option>
          </select>
        </Section>

        <Section label="Salary range (€/yr)">
          <div className="flex items-center gap-3">
            <input
              type="number"
              placeholder="Min"
              value={form.salary_min ?? ""}
              onChange={(e) => set("salary_min", Number(e.target.value) || null)}
              className="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
            />
            <span className="text-gray-400">–</span>
            <input
              type="number"
              placeholder="Max"
              value={form.salary_max ?? ""}
              onChange={(e) => set("salary_max", Number(e.target.value) || null)}
              className="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
            />
          </div>
        </Section>
      </div>

      <div className="mt-6 flex items-center gap-4">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save preferences"}
        </button>
        {saved && <span className="text-sm text-green-600">Saved!</span>}
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}
