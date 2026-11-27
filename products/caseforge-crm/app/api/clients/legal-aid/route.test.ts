
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { resetStubLegalAid } from "@/lib/stubLegalAid";
import { GET } from "./route";
import { POST } from "./send/route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/legal-aid?matter_id=${encodeURIComponent(matterId)}`);
}

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/clients/legal-aid/send", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

beforeEach(() => resetStubLegalAid());

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/legal-aid", () => {
  it("requires a matter_id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await GET(getReq(""))).status).toBe(400);
  });

  it("forwards the bearer token upstream and passes the answer back without it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const answer = { matter_id: "9001", application: { status: "missing" } };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(getReq("9001"));
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(JSON.parse(text)).toEqual(answer);
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/legal-aid?matter_id=9001`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("answers from the stub with no hub configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(getReq("9001"))).json();
    expect(body.application.status).toBe("found");
    expect(body.signature.status).toBe("not_sent");
  });
});

describe("POST /api/clients/legal-aid/send", () => {
  it("requires a matter", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await POST(postReq({}))).status).toBe(400);
  });

  it("passes the press to the hub with address_checked only when it is true", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await POST(postReq({ matter_id: "9001", address_checked: "yes" }));
    await POST(postReq({ matter_id: "9001", address_checked: true }));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/legal-aid/send`);
    expect(JSON.parse(init.body)).toEqual({ matter_id: "9001", by: "tailnet", address_checked: false });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).address_checked).toBe(true);
  });

  it("drafts in the stub and refuses a second press", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const first = await (await POST(postReq({ matter_id: "9001" }))).json();
    expect(first.ok).toBe(true);
    expect(first.section.signature.status).toBe("drafted");
    const second = await (await POST(postReq({ matter_id: "9001" }))).json();
    expect(second).toMatchObject({ ok: false, code: "sent" });
  });
});
