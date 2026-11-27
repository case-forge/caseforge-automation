
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET as statusGET } from "./status/route";
import { GET as recentGET } from "./recent/route";
import { POST as retryPOST } from "./retry/route";
import { POST as createPOST } from "./create/route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

function get(path: string): NextRequest {
  return new NextRequest(`http://localhost${path}`);
}
function post(path: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("input checks", () => {
  it("status needs a draft id, recent needs a matter, retry needs a draft id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await statusGET(get("/api/attendance-notes/status"))).status).toBe(400);
    expect((await recentGET(get("/api/attendance-notes/recent"))).status).toBe(400);
    expect((await retryPOST(post("/api/attendance-notes/retry", {}))).status).toBe(400);
  });
});

describe("stub lifecycle", () => {
  it("shows a new note as filing, then filed with a link, and lists it under its client", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.useFakeTimers();
    const created = await createPOST(post("/api/attendance-notes/create", { matter_id: "7001", caller: "court", attendance_folder: "CA", note_text: "Called." }));
    const { draft_id } = await created.json();

    const early = await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json();
    expect(early.state).toBe("filing");
    expect(early.an_url).toBeNull();

    vi.advanceTimersByTime(3000);
    const later = await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json();
    expect(later.state).toBe("filed");
    expect(later.an_url).toContain("http");

    const recent = await (await recentGET(get("/api/attendance-notes/recent?matter_id=7001"))).json();
    expect(recent.items.map((i: { draft_id: string }) => i.draft_id)).toContain(draft_id);
    expect((await (await recentGET(get("/api/attendance-notes/recent?matter_id=7002"))).json()).items).toEqual([]);
  });

  it("a failed note can be retried, and then files", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.useFakeTimers();
    const created = await createPOST(post("/api/attendance-notes/create", { matter_id: "7003", caller: "client", attendance_folder: "CA", note_text: "stubfail" }));
    const { draft_id } = await created.json();
    vi.advanceTimersByTime(3000);
    const failed = await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json();
    expect(failed.state).toBe("failed");
    expect(failed.error).toBeTruthy();

    await retryPOST(post("/api/attendance-notes/retry", { draft_id }));
    vi.advanceTimersByTime(3000);
    expect((await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json()).state).toBe("filed");
  });

  it("an unknown note is a 404", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await statusGET(get("/api/attendance-notes/status?draft_id=nope"))).status).toBe(404);
  });
});

describe("hub passthrough", () => {
  it("asks the hub for the last 48 hours with the bearer token", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    await recentGET(get("/api/attendance-notes/recent?matter_id=596"));
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/attendance-notes/recent?matter_id=596&hours=48");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token-not-a-real-secret");
  });
});
