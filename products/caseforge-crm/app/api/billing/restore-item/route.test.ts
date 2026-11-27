
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { POST as createPOST } from "../../attendance-notes/create/route";
import { POST as removePOST } from "../../attendance-notes/delete-billing/route";
import { GET as statusGET } from "../../attendance-notes/status/route";
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

describe("billing restore-item", () => {
  it("needs an item id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(post("/api/billing/restore-item", {}))).status).toBe(400);
    expect((await POST(post("/api/billing/restore-item", { item_id: " " }))).status).toBe(400);
  });

  it("lists a removed charge under Removed, out of the totals, and Undo puts it back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.useFakeTimers();
    const { draft_id } = await (await createPOST(post("/api/attendance-notes/create", { matter_id: "8811", caller: "court", attendance_folder: "CA", note_text: "Called." }))).json();
    vi.advanceTimersByTime(3000);
    await removePOST(post("/api/attendance-notes/delete-billing", { draft_id }));

    const removed = await (await billGET(get("/api/clients/bill-of-costs?matter_id=8811"))).json();
    expect(removed.item_count).toBe(0);
    expect(removed.total_net).toBe("0.00");
    expect(removed.removed).toHaveLength(1);
    expect(removed.removed[0].removed_utc).not.toBe("");
    expect(removed.removed[0].removed_by).not.toBe("");

    const res = await POST(post("/api/billing/restore-item", { item_id: removed.removed[0].item_id }));
    expect(res.status).toBe(200);
    expect((await res.json()).on_bill).toBe(true);

    const back = await (await billGET(get("/api/clients/bill-of-costs?matter_id=8811"))).json();
    expect(back.item_count).toBe(1);
    expect(back.removed).toEqual([]);
    expect((await (await statusGET(get(`/api/attendance-notes/status?draft_id=${draft_id}`))).json()).billing_removed).toBe(false);

    expect((await POST(post("/api/billing/restore-item", { item_id: removed.removed[0].item_id }))).status).toBe(200);
    expect((await POST(post("/api/billing/restore-item", { item_id: "nope" }))).status).toBe(422);
  });

  it("forwards to the hub with the bearer token", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ item_id: "b1", on_bill: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    await POST(post("/api/billing/restore-item", { item_id: "b1" }));
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/billing/restore-item");
    expect(JSON.parse(String(init.body))).toEqual({ item_id: "b1" });
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token-not-a-real-secret");
  });
});
