
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { POST as createPOST } from "../create/route";
import { GET as statusGET } from "../status/route";
import { GET as billGET } from "../../clients/bill-of-costs/route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

function post(path: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
function get(path: string): NextRequest {
  return new NextRequest(`http://localhost${path}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("delete-billing", () => {
  it("needs a draft id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(post("/api/attendance-notes/delete-billing", {}))).status).toBe(400);
    expect((await POST(post("/api/attendance-notes/delete-billing", { draft_id: "  " }))).status).toBe(400);
  });

  it("removes a filed note's line from the bill, leaves the note filed with its link, and is harmless twice", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.useFakeTimers();
    const { draft_id } = await (await createPOST(post("/api/attendance-notes/create", { matter_id: "8801", caller: "court", attendance_folder: "CA", note_text: "Called." }))).json();
    vi.advanceTimersByTime(3000);

    const before = await (await billGET(get("/api/clients/bill-of-costs?matter_id=8801"))).json();
    expect(before.item_count).toBe(1);
    expect(before.categories[0].items[0].attendance_draft_id).toBe(draft_id);

    const removed = await (await POST(post("/api/attendance-notes/delete-billing", { draft_id }))).json();
    expect(removed.billing_removed).toBe(true);
    expect(removed.state).toBe("filed");
    expect(removed.an_url).toContain("http");
    expect((await POST(post("/api/attendance-notes/delete-billing", { draft_id }))).status).toBe(200);

    expect((await (await billGET(get("/api/clients/bill-of-costs?matter_id=8801"))).json()).item_count).toBe(0);
    expect((await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json()).billing_removed).toBe(true);
    expect((await POST(post("/api/attendance-notes/delete-billing", { draft_id }))).status).toBe(200);
  });

  it("refuses a note that is still being filed, and one that does not exist", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.useFakeTimers();
    const { draft_id } = await (await createPOST(post("/api/attendance-notes/create", { matter_id: "8802", caller: "client", attendance_folder: "CA", note_text: "Called." }))).json();
    expect((await POST(post("/api/attendance-notes/delete-billing", { draft_id }))).status).toBe(422);
    expect((await POST(post("/api/attendance-notes/delete-billing", { draft_id: "nope" }))).status).toBe(422);
  });

  it("forwards to the hub with the bearer token", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ billing_removed: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    await POST(post("/api/attendance-notes/delete-billing", { draft_id: "d1" }));
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/attendance-notes/delete-billing");
    expect(JSON.parse(String(init.body))).toEqual({ draft_id: "d1" });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token-not-a-real-secret");
  });
});
