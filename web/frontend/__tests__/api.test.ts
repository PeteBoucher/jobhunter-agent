import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createApplication,
  deleteSkill,
  getJob,
  getJobs,
  updateApplication,
} from "../lib/api";

const TOKEN = "test-token";

function mockFetch(body: unknown, status = 200) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("getJobs", () => {
  it("sends Authorization header", async () => {
    const spy = mockFetch([]);
    await getJobs(TOKEN);
    expect(spy.mock.calls[0][1]?.headers).toMatchObject({
      Authorization: "Bearer test-token",
    });
  });

  it("serialises query params", async () => {
    const spy = mockFetch([]);
    await getJobs(TOKEN, { keywords: "engineer", remote: "remote", page: 2 });
    const url = spy.mock.calls[0][0] as string;
    expect(url).toContain("keywords=engineer");
    expect(url).toContain("remote=remote");
    expect(url).toContain("page=2");
  });

  it("appends multiple exclude_statuses", async () => {
    const spy = mockFetch([]);
    await getJobs(TOKEN, { exclude_statuses: ["rejected", "withdrawn"] });
    const url = spy.mock.calls[0][0] as string;
    expect(url).toContain("exclude_statuses=rejected");
    expect(url).toContain("exclude_statuses=withdrawn");
  });
});

describe("getJob", () => {
  it("fetches the correct job URL", async () => {
    const spy = mockFetch({ id: 42 });
    await getJob(TOKEN, 42);
    expect(spy.mock.calls[0][0]).toContain("/jobs/42");
  });
});

describe("createApplication", () => {
  it("POSTs with correct body", async () => {
    const spy = mockFetch({ id: 1 });
    await createApplication(TOKEN, 99, "applied", "Great role");
    const body = JSON.parse(spy.mock.calls[0][1]?.body as string);
    expect(body).toEqual({ job_id: 99, status: "applied", notes: "Great role" });
  });
});

describe("updateApplication", () => {
  it("PATCHes the correct URL", async () => {
    const spy = mockFetch({ id: 7 });
    await updateApplication(TOKEN, 7, "offer");
    expect(spy.mock.calls[0][0]).toContain("/applications/7");
    expect(spy.mock.calls[0][1]?.method).toBe("PATCH");
  });
});

describe("deleteSkill", () => {
  it("sends DELETE to the correct URL", async () => {
    const spy = mockFetch(null, 204);
    await deleteSkill(TOKEN, 42);
    expect(spy.mock.calls[0][0]).toContain("/profile/skills/42");
    expect(spy.mock.calls[0][1]?.method).toBe("DELETE");
  });

  it("sends Authorization header", async () => {
    const spy = mockFetch(null, 204);
    await deleteSkill(TOKEN, 7);
    expect(spy.mock.calls[0][1]?.headers).toMatchObject({
      Authorization: "Bearer test-token",
    });
  });

  it("resolves to undefined on 204", async () => {
    mockFetch(null, 204);
    await expect(deleteSkill(TOKEN, 1)).resolves.toBeUndefined();
  });

  it("throws on 404 (skill not found)", async () => {
    mockFetch({ detail: "Skill not found" }, 404);
    await expect(deleteSkill(TOKEN, 999)).rejects.toThrow("API 404");
  });

  it("throws on 401 (unauthenticated)", async () => {
    mockFetch({ detail: "Not authenticated" }, 401);
    await expect(deleteSkill(TOKEN, 1)).rejects.toThrow("API 401");
  });
});

describe("error handling", () => {
  it("throws on non-ok response", async () => {
    mockFetch({ detail: "Not found" }, 404);
    await expect(getJob(TOKEN, 999)).rejects.toThrow("API 404");
  });
});
