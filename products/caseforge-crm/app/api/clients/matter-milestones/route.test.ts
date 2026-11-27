
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function getReq(query: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-milestones?${query}`);
}

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/clients/matter-milestones", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-milestones", () => {
  it("requires a matter_id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await GET(getReq("matter_id="))).status).toBe(400);
  });

  it("forwards the token upstream, asks the hub to search Sent Items only on live=1, and hides the token from the answer", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const answer = { matter_id: "9001", milestones: {} };
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const live = await GET(getReq("matter_id=9001&live=1"));
    const text = await live.text();
    expect(JSON.parse(text)).toEqual(answer);
    expect(text).not.toContain(TOKEN);
    await GET(getReq("matter_id=9001"));
    const [liveUrl, init] = fetchMock.mock.calls[0];
    expect(String(liveUrl)).toBe(`${HUB}/client-viewer/matter-milestones?matter_id=9001&live=true`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(String(fetchMock.mock.calls[1][0])).toBe(`${HUB}/client-viewer/matter-milestones?matter_id=9001&live=false`);
  });

  it("answers from the stub with every milestone", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(getReq("matter_id=9001"))).json();
    expect(Object.keys(body.milestones)).toEqual(["contacted", "papers_signed", "filed", "service_requested", "served", "legal_aid_done", "invoice_paid", "laa_interim_cert", "laa_final_cert"]);
    expect(body.milestones.contacted.at).not.toBe("");
    expect(body.milestones.contacted.can_set).toBe(false);
    expect(body.milestones.invoice_paid.can_set).toBe(true);

    expect(body.milestones.legal_aid_done.at).not.toBe("");
    expect(body.milestones.legal_aid_done.can_set).toBe(true);
  });
});

describe("POST /api/clients/matter-milestones", () => {
  it("refuses a missing matter and any milestone the system records itself", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(postReq({ milestone: "invoice_paid" }))).status).toBe(400);
    for (const milestone of ["contacted", "papers_signed", "filed", "nonsense", ""]) {
      expect((await POST(postReq({ matter_id: "9001", milestone }))).status, milestone).toBe(400);
    }
  });

  it("passes the press to the hub with no person named, and clear only when it is true", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await POST(postReq({ matter_id: "9001", milestone: "invoice_paid", at: "2026-10-20T09:00", clear: "yes", by: "someone else" }));
    await POST(postReq({ matter_id: "9001", milestone: "legal_aid_done", clear: true }));
    const first = JSON.parse(fetchMock.mock.calls[0][1].body);
    const second = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(first).toEqual({ matter_id: "9001", milestone: "invoice_paid", at: "2026-10-20T09:00", clear: false });
    expect(second).toEqual({ matter_id: "9001", milestone: "legal_aid_done", at: "", clear: true });
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${HUB}/client-viewer/matter-milestones`);
  });

  it("records, then clears, a time in the stub and refuses one in the future", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const set = await (await POST(postReq({ matter_id: "9002", milestone: "invoice_paid", at: "2026-10-20T09:00:00Z" }))).json();
    expect(set.milestones.invoice_paid.at).toBe("2026-10-20T09:00:00Z");
    expect(set.milestones.invoice_paid.manual).toBe(true);
    const cleared = await (await POST(postReq({ matter_id: "9002", milestone: "invoice_paid", clear: true }))).json();
    expect(cleared.milestones.invoice_paid.at).toBe("");
    expect((await POST(postReq({ matter_id: "9002", milestone: "invoice_paid", at: "2999-01-01T00:00:00Z" }))).status).toBe(422);
  });
});
