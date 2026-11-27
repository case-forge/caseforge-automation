
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { addDaysIso, londonTodayIso } from "@/lib/hearings";
import { stubUseCalendarFixtures } from "@/lib/stub";
import { GET as listGet, POST as createPost } from "./route";
import { GET as reviewGet } from "./review/route";
import { POST as updatePost } from "./update/route";
import { POST as statusPost } from "./status/route";
import { POST as resolvePost } from "./review-resolve/route";
import { GET as historyGet } from "./history/route";
import { GET as icsGet } from "./ics/route";
import { POST as linkPost } from "./link/route";
import { GET as suggestGet } from "./suggest-matters/route";
import { GET as leadsGet } from "./leads/route";
import { POST as leadResolvePost } from "./leads/resolve/route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

const EDITOR = "solicitor@example.invalid";

function useHub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

function get(path: string): NextRequest {
  return new NextRequest(`http://localhost${path}`);
}

function post(path: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function wideRange(): string {
  const today = londonTodayIso();
  return `from=${addDaysIso(today, -60)}&to=${addDaysIso(today, 60)}`;
}

function upstreamJson(body: unknown, status = 200) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

beforeEach(() => {
  stubUseCalendarFixtures();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.mocked(resolveIdentityForRoute).mockClear();
});

describe("GET /api/hearings", () => {
  it("rejects a missing, malformed, reversed or oversized range", async () => {
    useHub();
    for (const q of ["", "?from=2026-09-01", "?from=2026-09-31&to=2026-10-01", "?from=2026-10-01&to=2026-09-01", "?from=2020-01-01&to=2026-12-31"]) {
      expect((await listGet(get(`/api/hearings${q}`))).status).toBe(400);
    }
  });

  it("rejects a non-numeric matter_id", async () => {
    useHub();
    expect((await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30&matter_id=abc"))).status).toBe(400);
  });

  it("forwards range and matter upstream with the token and identity, never to the browser", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearings: [], needs_review_count: 0 });
    vi.stubGlobal("fetch", fetchSpy);

    const res = await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30&matter_id=42"));
    const text = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings?from=2026-09-01&to=2026-09-30&matter_id=42`);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers["Remote-User"]).toBe("solicitor@example.invalid");
    expect(text).not.toContain(TOKEN);
  });

  it("answers the identity rejection without calling the hub", async () => {
    useHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    vi.mocked(resolveIdentityForRoute).mockResolvedValueOnce({
      remoteUser: null,
      rejection: Response.json({ error: "identity verification failed" }, { status: 403 }),
    });
    expect((await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30"))).status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("serves the seeded stub and never fetches when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await listGet(get(`/api/hearings?${wideRange()}`));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.hearings.length).toBeGreaterThan(10);
    expect(body.needs_review_count).toBeGreaterThan(0);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect((await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30"))).status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("propagates an upstream failure status without leaking its body", async () => {
    useHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 500 })));
    const res = await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30"));
    expect(res.status).toBe(500);
    expect(await res.text()).not.toContain("secret upstream detail");
  });

  it("returns 502 when the hub is unreachable or answers with junk", async () => {
    useHub();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("connect refused"); }));
    expect((await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30"))).status).toBe(502);
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 200 })));
    expect((await listGet(get("/api/hearings?from=2026-09-01&to=2026-09-30"))).status).toBe(502);
  });
});

describe("POST /api/hearings (create)", () => {
  const valid = { case_ref: "ZZ25F99999", hearing_date: "2026-10-01", hearing_time: "10:00" };

  it("requires a case number and a date", async () => {
    useHub();
    expect((await createPost(post("/api/hearings", { ...valid, case_ref: "" }))).status).toBe(400);
    expect((await createPost(post("/api/hearings", { ...valid, hearing_date: undefined }))).status).toBe(400);
    expect((await createPost(post("/api/hearings", "not json"))).status).toBe(400);
  });

  it("refuses fields the hearing does not have, rather than forwarding them", async () => {
    useHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const res = await createPost(post("/api/hearings", { ...valid, hearing_id: 5, status: "vacated" }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toContain("hearing_id");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards the fields and the signed-in editor, and surfaces the hub's own detail on refusal", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearing: { hearing_id: 1 } });
    vi.stubGlobal("fetch", fetchSpy);
    expect((await createPost(post("/api/hearings", valid))).status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ ...valid, edited_by: EDITOR });

    vi.stubGlobal("fetch", upstreamJson({ detail: "hearing date is a weekend" }, 422));
    const refused = await createPost(post("/api/hearings", valid));
    expect(refused.status).toBe(422);
    expect((await refused.json()).error).toBe("hearing date is a weekend");
  });

  it("creates in the stub and the new hearing then lists", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await createPost(post("/api/hearings", valid));
    expect(res.status).toBe(200);
    const { hearing } = await res.json();
    expect(hearing.case_ref).toBe("ZZ25F99999");
    expect(hearing.source_kind).toBe("manual");
    const list = await (await listGet(get("/api/hearings?from=2026-10-01&to=2026-10-01"))).json();
    expect(list.hearings.map((h: { hearing_id: number }) => h.hearing_id)).toContain(hearing.hearing_id);
  });
});

describe("POST /api/hearings/update", () => {
  it("validates id and edits", async () => {
    useHub();
    const ok = { hearing_id: 3, edits: { court: "Leeds" } };
    expect((await updatePost(post("/api/hearings/update", { ...ok, hearing_id: 0 }))).status).toBe(400);
    expect((await updatePost(post("/api/hearings/update", { ...ok, edits: {} }))).status).toBe(400);
    expect((await updatePost(post("/api/hearings/update", { ...ok, edits: { review_state: "ok" } }))).status).toBe(400);
  });

  it("forwards only the named edits", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearing: { hearing_id: 3 } });
    vi.stubGlobal("fetch", fetchSpy);
    await updatePost(post("/api/hearings/update", { hearing_id: "3", edits: { hearing_time: "11:30" }, note: "moved" }));
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/update`);
    expect(JSON.parse(String(init.body))).toEqual({ hearing_id: 3, edits: { hearing_time: "11:30" }, edited_by: EDITOR, note: "moved" });
  });

  it("updates the stub and records history", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await updatePost(post("/api/hearings/update", { hearing_id: 1, edits: { court: "Changed Court" } }));
    expect((await res.json()).hearing.court).toBe("Changed Court");
    const history = await (await historyGet(get("/api/hearings/history?hearing_id=1"))).json();
    expect(history.events[0]).toMatchObject({ action: "updated", actor: EDITOR });
  });

  it("answers 422 for a stub-side refusal", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await updatePost(post("/api/hearings/update", { hearing_id: 1, edits: { hearing_date: "2026-02-30" } }));
    expect(res.status).toBe(422);
  });
});

describe("POST /api/hearings/status", () => {
  it("accepts only the three statuses", async () => {
    useHub();
    const base = { hearing_id: 2 };
    expect((await statusPost(post("/api/hearings/status", { ...base, status: "deleted" }))).status).toBe(400);
    expect((await statusPost(post("/api/hearings/status", { ...base, status: "" }))).status).toBe(400);
  });

  it("vacates and reinstates in the stub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const vacated = await (await statusPost(post("/api/hearings/status", { hearing_id: 2, status: "vacated" }))).json();
    expect(vacated.hearing.status).toBe("vacated");
    const back = await (await statusPost(post("/api/hearings/status", { hearing_id: 2, status: "scheduled" }))).json();
    expect(back.hearing.status).toBe("scheduled");
  });
});

describe("review queue routes", () => {
  it("lists only hearings needing review", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await reviewGet(get("/api/hearings/review"))).json();
    expect(body.hearings.length).toBeGreaterThan(0);
    expect(body.hearings.every((h: { review_state: string }) => h.review_state === "needs_review")).toBe(true);
  });

  it("proxies the review list upstream with the token", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearings: [] });
    vi.stubGlobal("fetch", fetchSpy);
    await reviewGet(get("/api/hearings/review"));
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/review`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("validates the resolve action, and confirm-with-edits then dismiss close the item", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await resolvePost(post("/api/hearings/review-resolve", { hearing_id: 5, action: "approve" }))).status).toBe(400);
    expect((await resolvePost(post("/api/hearings/review-resolve", { hearing_id: 5, action: "confirm", edits: { bogus: 1 } }))).status).toBe(400);

    const confirmed = await (await resolvePost(post("/api/hearings/review-resolve", { hearing_id: 5, action: "confirm", edits: { hearing_time: "10:00" } }))).json();
    expect(confirmed.hearing).toMatchObject({ review_state: "ok", hearing_time: "10:00" });
    const dismissed = await (await resolvePost(post("/api/hearings/review-resolve", { hearing_id: 6, action: "dismiss" }))).json();
    expect(dismissed.hearing.review_state).toBe("dismissed");

    const remaining = await (await reviewGet(get("/api/hearings/review"))).json();
    const ids = remaining.hearings.map((h: { hearing_id: number }) => h.hearing_id);
    expect(ids).not.toContain(5);
    expect(ids).not.toContain(6);
  });

  it("forwards a resolve upstream with edits only when there are some", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearing: { hearing_id: 5 } });
    vi.stubGlobal("fetch", fetchSpy);
    await resolvePost(post("/api/hearings/review-resolve", { hearing_id: 5, action: "dismiss" }));
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ hearing_id: 5, action: "dismiss", edited_by: EDITOR });
  });
});

describe("POST /api/hearings/link", () => {
  const ok = { hearing_id: 12, matter_id: 9001 };

  it("validates hearing and matter, and never sends a non-numeric matter id", async () => {
    useHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect((await linkPost(post("/api/hearings/link", { ...ok, hearing_id: 0 }))).status).toBe(400);
    for (const matter_id of ["STUB-001", "", null, 0, -1, "12x", 1.5]) {
      expect((await linkPost(post("/api/hearings/link", { ...ok, matter_id }))).status).toBe(400);
    }
    expect((await linkPost(post("/api/hearings/link", "nope"))).status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards exactly the three fields with the token and identity, and returns the hub's reference", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearing: { hearing_id: 12 }, reference: "conflict" });
    vi.stubGlobal("fetch", fetchSpy);
    const res = await linkPost(post("/api/hearings/link", { ...ok, matter_id: "9001", extra: "dropped" }));
    expect((await res.json()).reference).toBe("conflict");
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/link`);
    expect(JSON.parse(String(init.body))).toEqual({ hearing_id: 12, matter_id: 9001, edited_by: EDITOR });
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers["Remote-User"]).toBe("solicitor@example.invalid");
  });

  it("surfaces only the hub's short detail on refusal", async () => {
    useHub();
    vi.stubGlobal("fetch", upstreamJson({ detail: "matter not found", trace: "secret" }, 404));
    const res = await linkPost(post("/api/hearings/link", ok));
    expect(res.status).toBe(404);
    const text = await res.text();
    expect(text).toContain("matter not found");
    expect(text).not.toContain("secret");
  });

  it("in the stub links every unlinked hearing sharing the case number, and reports conflict", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const before = (await (await listGet(get(`/api/hearings?${wideRange()}`))).json()).hearings as { hearing_id: number; matter_id: number | null; case_ref: string }[];
    const target = before.find((h) => h.matter_id === null && h.case_ref === "ZZ25F22222")!;
    const siblings = before.filter((h) => h.matter_id === null && h.case_ref === "ZZ25F22222");
    expect(siblings.length).toBe(2);

    const res = await linkPost(post("/api/hearings/link", { hearing_id: target.hearing_id, matter_id: 9001 }));
    const body = await res.json();
    expect(body.reference).toBe("recorded");
    expect(body.hearing.matter_id).toBe(9001);
    expect(body.hearing.client_name).toBe("Stub Testperson");

    const after = (await (await listGet(get(`/api/hearings?${wideRange()}`))).json()).hearings as { case_ref: string; matter_id: number | null }[];
    expect(after.filter((h) => h.case_ref === "ZZ25F22222").every((h) => h.matter_id === 9001)).toBe(true);
    expect(after.filter((h) => h.matter_id === null).some((h) => h.case_ref === "ZZ25F22222")).toBe(false);

    const other = before.find((h) => h.matter_id === null && h.case_ref === "ZZ26P33333")!;
    const conflict = await (await linkPost(post("/api/hearings/link", { hearing_id: other.hearing_id, matter_id: 999 }))).json();
    expect(conflict.reference).toBe("conflict");
    expect(conflict.hearing.matter_id).toBe(999);
  });

  it("an unlinked hearing is a normal one in the stub: not in the review queue", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const queue = (await (await reviewGet(get("/api/hearings/review"))).json()).hearings as { matter_id: number | null; review_state: string }[];
    expect(queue.every((h) => h.review_state === "needs_review")).toBe(true);
    expect(queue.some((h) => h.matter_id === null)).toBe(false);
  });
});

describe("GET /api/hearings/suggest-matters", () => {
  it("requires a numeric hearing_id", async () => {
    useHub();
    expect((await suggestGet(get("/api/hearings/suggest-matters"))).status).toBe(400);
    expect((await suggestGet(get("/api/hearings/suggest-matters?hearing_id=x"))).status).toBe(400);
  });

  it("proxies upstream with the token and identity", async () => {
    useHub();
    const fetchSpy = upstreamJson({ suggestions: [{ matter_id: 5, client_name: "A B", matched_on: "surname", exact: false }] });
    vi.stubGlobal("fetch", fetchSpy);
    const res = await suggestGet(get("/api/hearings/suggest-matters?hearing_id=12"));
    expect((await res.json()).suggestions[0].matter_id).toBe(5);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/suggest-matters?hearing_id=12`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.invalid");
  });

  it("fails closed when unconfigured and does not leak an upstream failure", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    expect((await suggestGet(get("/api/hearings/suggest-matters?hearing_id=1"))).status).toBe(503);
    useHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 500 })));
    const res = await suggestGet(get("/api/hearings/suggest-matters?hearing_id=1"));
    expect(res.status).toBe(500);
    expect(await res.text()).not.toContain("secret upstream detail");
  });

  it("in the stub suggests by name for an unlinked hearing and never for a linked one", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const list = (await (await listGet(get(`/api/hearings?${wideRange()}`))).json()).hearings as { hearing_id: number; matter_id: number | null; case_ref: string }[];
    const unlinked = list.find((h) => h.matter_id === null && h.case_ref === "ZZ25F22222")!;
    const s = (await (await suggestGet(get(`/api/hearings/suggest-matters?hearing_id=${unlinked.hearing_id}`))).json()).suggestions;
    expect(s.length).toBeGreaterThan(0);
    expect(s[0]).toMatchObject({ matter_id: 9001, exact: false });
    expect(s[0].matched_on).toBeTruthy();
    const linked = list.find((h) => h.matter_id !== null)!;
    expect((await (await suggestGet(get(`/api/hearings/suggest-matters?hearing_id=${linked.hearing_id}`))).json()).suggestions).toEqual([]);
  });
});

describe("a client's hearings (matter_id filter)", () => {
  const today = londonTodayIso();
  const q = (matter?: string) => `from=${addDaysIso(today, -730)}&to=${addDaysIso(today, 1095)}${matter ? `&matter_id=${matter}` : ""}`;

  it("accepts the two-years-back, three-ahead window for one matter and forwards it", async () => {
    useHub();
    const fetchSpy = upstreamJson({ hearings: [], needs_review_count: 0 });
    vi.stubGlobal("fetch", fetchSpy);
    expect((await listGet(get(`/api/hearings?${q("42")}`))).status).toBe(200);
    const [url] = fetchSpy.mock.calls[0] as unknown as [URL];
    expect(String(url)).toContain("matter_id=42");
    expect((await listGet(get(`/api/hearings?${q()}`))).status).toBe(400);
  });

  it("in the stub, returns only that matter's hearings, upcoming and past", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const mine = (await (await listGet(get(`/api/hearings?${q("9001")}`))).json()).hearings as { matter_id: number; hearing_date: string; status: string }[];
    expect(mine.length).toBeGreaterThanOrEqual(10);
    expect(mine.every((h) => h.matter_id === 9001)).toBe(true);
    expect(mine.some((h) => h.hearing_date >= today)).toBe(true);
    expect(mine.filter((h) => h.hearing_date < today).length).toBeGreaterThan(5);
    expect(mine.some((h) => h.status === "vacated")).toBe(true);
    const none = (await (await listGet(get(`/api/hearings?${q("9002")}`))).json()).hearings;
    expect(none).toEqual([]);
  });

  it("a hearing added for the matter in the stub then lists under it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const created = await (await createPost(post("/api/hearings", { case_ref: "ZZ21D00000", hearing_date: addDaysIso(today, 9), matter_id: 9001 }))).json();
    expect(created.hearing.matter_id).toBe(9001);
    const mine = (await (await listGet(get(`/api/hearings?${q("9001")}`))).json()).hearings as { hearing_id: number }[];
    expect(mine.map((h) => h.hearing_id)).toContain(created.hearing.hearing_id);
  });
});

describe("hearing leads (emails to check)", () => {
  it("lists the leads upstream with the token and identity, and does not leak a failure", async () => {
    useHub();
    const fetchSpy = upstreamJson({ leads: [{ lead_id: 1, source_subject: "s", source_received_utc: "", source_web_link: "", reason: "r", state: "open", created_utc: "" }] });
    vi.stubGlobal("fetch", fetchSpy);
    const res = await leadsGet(get("/api/hearings/leads"));
    expect((await res.json()).leads).toHaveLength(1);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/leads`);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers["Remote-User"]).toBe("solicitor@example.invalid");

    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 500 })));
    const failed = await leadsGet(get("/api/hearings/leads"));
    expect(failed.status).toBe(500);
    expect(await failed.text()).not.toContain("secret upstream detail");
  });

  it("fails closed when unconfigured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    expect((await leadsGet(get("/api/hearings/leads"))).status).toBe(503);
  });

  it("validates a resolve request and forwards exactly lead_id, action and edited_by", async () => {
    useHub();
    const fetchSpy = upstreamJson({ lead: { lead_id: 3, state: "done" } });
    vi.stubGlobal("fetch", fetchSpy);
    const ok = { lead_id: 3, action: "done" };
    expect((await leadResolvePost(post("/api/hearings/leads/resolve", { ...ok, lead_id: 0 }))).status).toBe(400);
    for (const action of ["reopen", "", "resolved", undefined]) {
      expect((await leadResolvePost(post("/api/hearings/leads/resolve", { ...ok, action }))).status).toBe(400);
    }
    expect((await leadResolvePost(post("/api/hearings/leads/resolve", "nope"))).status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();

    expect((await leadResolvePost(post("/api/hearings/leads/resolve", { ...ok, lead_id: "3", extra: "dropped" }))).status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/leads/resolve`);
    expect(JSON.parse(String(init.body))).toEqual({ lead_id: 3, action: "done", edited_by: EDITOR });
  });

  it("surfaces only the hub's short detail when a resolve is refused", async () => {
    useHub();
    vi.stubGlobal("fetch", upstreamJson({ detail: "lead 9 not found", trace: "secret" }, 404));
    const res = await leadResolvePost(post("/api/hearings/leads/resolve", { lead_id: 9, action: "dismissed" }));
    expect(res.status).toBe(404);
    const text = await res.text();
    expect(text).toContain("lead 9 not found");
    expect(text).not.toContain("secret");
  });

  it("in the stub: leads carry realistic emails, closing one removes it, and the counts follow", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const before = (await (await leadsGet(get("/api/hearings/leads"))).json()).leads as { lead_id: number; source_web_link: string; state: string }[];
    expect(before.length).toBeGreaterThanOrEqual(2);
    expect(before.every((l) => l.state === "open")).toBe(true);
    expect(before.some((l) => l.source_web_link.startsWith("https://"))).toBe(true);

    const list = await (await listGet(get(`/api/hearings?${wideRange()}`))).json();
    expect(list.open_leads_count).toBe(before.length);
    expect((await (await reviewGet(get("/api/hearings/review"))).json()).open_leads_count).toBe(before.length);

    const done = await (await leadResolvePost(post("/api/hearings/leads/resolve", { lead_id: before[0].lead_id, action: "done" }))).json();
    expect(done.lead.state).toBe("done");
    const dismissed = await (await leadResolvePost(post("/api/hearings/leads/resolve", { lead_id: before[1].lead_id, action: "dismissed" }))).json();
    expect(dismissed.lead.state).toBe("dismissed");

    const after = (await (await leadsGet(get("/api/hearings/leads"))).json()).leads as { lead_id: number }[];
    expect(after.map((l) => l.lead_id)).not.toContain(before[0].lead_id);
    expect(after.map((l) => l.lead_id)).not.toContain(before[1].lead_id);
    expect((await (await listGet(get(`/api/hearings?${wideRange()}`))).json()).open_leads_count).toBe(after.length);

    expect((await leadResolvePost(post("/api/hearings/leads/resolve", { lead_id: 999, action: "done" }))).status).toBe(422);
  });
});

describe("GET /api/hearings/history", () => {
  it("requires a numeric hearing_id", async () => {
    useHub();
    expect((await historyGet(get("/api/hearings/history"))).status).toBe(400);
    expect((await historyGet(get("/api/hearings/history?hearing_id=x"))).status).toBe(400);
  });
});

describe("GET /api/hearings/ics", () => {
  it("validates the range", async () => {
    useHub();
    expect((await icsGet(get("/api/hearings/ics?from=bad&to=2026-09-30"))).status).toBe(400);
  });

  it("streams the hub's file through with its content-type and disposition", async () => {
    useHub();
    const fetchSpy = vi.fn(
      async () =>
        new Response("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", {
          status: 200,
          headers: { "content-type": "text/calendar; charset=utf-8", "content-disposition": 'attachment; filename="from-hub.ics"' },
        }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    const res = await icsGet(get("/api/hearings/ics?from=2026-09-01&to=2026-09-30"));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("text/calendar; charset=utf-8");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="from-hub.ics"');
    expect(await res.text()).toContain("BEGIN:VCALENDAR");
    const [url] = fetchSpy.mock.calls[0] as unknown as [URL];
    expect(String(url)).toBe(`${HUB}/client-viewer/hearings/ics?from=2026-09-01&to=2026-09-30`);
  });

  it("names the download itself when the hub sends no disposition", async () => {
    useHub();

    vi.stubGlobal("fetch", vi.fn(async () => new Response(new TextEncoder().encode("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"), { status: 200 })));
    const res = await icsGet(get("/api/hearings/ics?from=2026-09-01&to=2026-09-30"));
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="hearings-2026-09-01-to-2026-09-30.ics"');
    expect(res.headers.get("content-type")).toContain("text/calendar");
  });

  it("serves a stub calendar file", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await icsGet(get(`/api/hearings/ics?${wideRange()}`));
    const text = await res.text();
    expect(text.startsWith("BEGIN:VCALENDAR")).toBe(true);
    expect(text).toContain("BEGIN:VEVENT");
    expect(text).not.toContain("(vacated)");
  });
});
