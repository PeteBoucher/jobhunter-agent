/**
 * Typed API client for the jobhunter FastAPI backend.
 * All methods require a valid API token (from next-auth session).
 */
import type { Application, ApplicationStatus, Job, Preferences, User } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(
  path: string,
  token: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export function getMe(token: string): Promise<User> {
  return request<User>("/auth/me", token);
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

export interface JobsParams {
  keywords?: string;
  location?: string;
  remote?: string;
  min_score?: number;
  sort?: "score" | "date";
  page?: number;
  page_size?: number;
  exclude_statuses?: string[];
}

export function getJobs(token: string, params: JobsParams = {}): Promise<Job[]> {
  const qs = new URLSearchParams();
  if (params.keywords) qs.set("keywords", params.keywords);
  if (params.location) qs.set("location", params.location);
  if (params.remote) qs.set("remote", params.remote);
  if (params.min_score != null) qs.set("min_score", String(params.min_score));
  if (params.sort) qs.set("sort", params.sort);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  params.exclude_statuses?.forEach((s) => qs.append("exclude_statuses", s));
  return request<Job[]>(`/jobs?${qs}`, token);
}

export function getJob(token: string, id: number): Promise<Job> {
  return request<Job>(`/jobs/${id}`, token);
}

// ── Profile ──────────────────────────────────────────────────────────────────

export function getProfile(token: string): Promise<User> {
  return request<User>("/profile", token);
}

export function updateProfile(
  token: string,
  body: { name?: string; title?: string; location?: string }
): Promise<User> {
  return request<User>("/profile", token, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function uploadCV(token: string, file: File): Promise<User> {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_URL}/profile/cv`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  }).then((res) => {
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json();
  });
}

// ── Preferences ──────────────────────────────────────────────────────────────

export function getPreferences(token: string): Promise<Preferences> {
  return request<Preferences>("/preferences", token);
}

export function updatePreferences(
  token: string,
  body: Partial<Preferences>
): Promise<Preferences> {
  return request<Preferences>("/preferences", token, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ── Applications ─────────────────────────────────────────────────────────────

export function getApplications(
  token: string,
  status?: ApplicationStatus
): Promise<Application[]> {
  const qs = status ? `?status=${status}` : "";
  return request<Application[]>(`/applications${qs}`, token);
}

export function createApplication(
  token: string,
  job_id: number,
  status: ApplicationStatus = "applied",
  notes?: string
): Promise<Application> {
  return request<Application>("/applications", token, {
    method: "POST",
    body: JSON.stringify({ job_id, status, notes }),
  });
}

export function updateApplication(
  token: string,
  id: number,
  status: ApplicationStatus,
  notes?: string
): Promise<Application> {
  return request<Application>(`/applications/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify({ status, notes }),
  });
}

export function deleteApplication(token: string, id: number): Promise<void> {
  return request<void>(`/applications/${id}`, token, { method: "DELETE" });
}

// ── Account ───────────────────────────────────────────────────────────────────

export async function deleteAccount(token: string): Promise<void> {
  const res = await fetch(`${API_URL}/profile`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
}
