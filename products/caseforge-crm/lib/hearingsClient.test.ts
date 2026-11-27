import { afterEach, describe, expect, it, vi } from "vitest";
import { createHearing, fetchHearings, fetchLeads, resolveLead, resolveReview, setHearingStatus, updateHearing } from "./hearingsClient";

function respond(body: unknown, init: ResponseInit = { status: 200 }, contentType = "application/json") {
  return vi.fn(async () => new Response(typeof body === "string" ? body : JSON.stringify(body), { ...init, headers: { "content-type": contentType } }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("hearingsClient", () => {
  it("builds the range query and returns the parsed body", async () => {
    const spy = respond({ hearings: [], needs_review_count: 2 });
    vi.stubGlobal("fetch", spy);
    const out = await fetchHearings("2026-09-01", "2026-09-30", undefined, 7);
    expect(out.needs_review_count).toBe(2);
    expect((spy.mock.calls[0] as unknown as [string])[0]).toBe("/api/hearings?from=2026-09-01&to=2026-09-30&matter_id=7");
  });

  it("throws the route's own error message", async () => {
    vi.stubGlobal("fetch", respond({ error: "date range is too long" }, { status: 400 }));
    await expect(fetchHearings("2020-01-01", "2026-09-30")).rejects.toThrow("date range is too long");
  });

  it("treats an HTML answer (a lapsed Access session) as an expired session and raises the stale signal", async () => {
    const listener = vi.fn();
    const target = new EventTarget();
    vi.stubGlobal("window", Object.assign(target, { dispatchEvent: (e: Event) => { listener(e.type); return true; } }));
    vi.stubGlobal("fetch", respond("<html><a href='https://x.cloudflareaccess.com/login'></a></html>", { status: 401 }, "text/html"));
    await expect(fetchHearings("2026-09-01", "2026-09-30")).rejects.toThrow("session has expired");
    expect(listener).toHaveBeenCalledWith("caseforge:session-stale");
    vi.unstubAllGlobals();
  });

  it("does not claim an expiry for a 502 page or a dropped connection", async () => {
    const listener = vi.fn();
    vi.stubGlobal("window", Object.assign(new EventTarget(), { dispatchEvent: (e: Event) => { listener(e.type); return true; } }));
    vi.stubGlobal("fetch", respond("<h1>Bad gateway</h1>", { status: 502 }, "text/html"));
    await expect(fetchHearings("2026-09-01", "2026-09-30")).rejects.toThrow("Could not reach the server");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(fetchHearings("2026-09-01", "2026-09-30")).rejects.toThrow("Could not reach the server");
    expect(listener).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("does not raise the stale signal for an aborted request", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new DOMException("aborted", "AbortError"); }));
    await expect(fetchHearings("2026-09-01", "2026-09-30")).rejects.toMatchObject({ name: "AbortError" });
  });

  it("fetches the leads and closes one without naming anyone (the server records the signed-in person)", async () => {
    const spy = respond({ leads: [] });
    vi.stubGlobal("fetch", spy);
    await fetchLeads();
    await resolveLead(4, "dismissed");
    const calls = spy.mock.calls as unknown as [string, RequestInit | undefined][];
    expect(calls[0][0]).toBe("/api/hearings/leads");
    expect(calls[1][0]).toBe("/api/hearings/leads/resolve");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ lead_id: 4, action: "dismissed" });
  });

  it("posts each write with only the fields given, never a name", async () => {
    const spy = respond({ hearing: { hearing_id: 1 } });
    vi.stubGlobal("fetch", spy);
    await createHearing({ case_ref: "ZZ24F11111", hearing_date: "2026-10-01" });
    await updateHearing(1, { court: "Leeds" }, "moved");
    await setHearingStatus(1, "vacated");
    await resolveReview(1, "confirm");
    await resolveReview(1, "confirm", { hearing_time: "10:00" });
    const bodies = (spy.mock.calls as unknown as [string, RequestInit][]).map(([url, init]) => [url, JSON.parse(String(init.body))]);
    expect(bodies).toEqual([
      ["/api/hearings", { case_ref: "ZZ24F11111", hearing_date: "2026-10-01" }],
      ["/api/hearings/update", { hearing_id: 1, edits: { court: "Leeds" }, note: "moved" }],
      ["/api/hearings/status", { hearing_id: 1, status: "vacated" }],
      ["/api/hearings/review-resolve", { hearing_id: 1, action: "confirm" }],
      ["/api/hearings/review-resolve", { hearing_id: 1, action: "confirm", edits: { hearing_time: "10:00" } }],
    ]);
  });
});
