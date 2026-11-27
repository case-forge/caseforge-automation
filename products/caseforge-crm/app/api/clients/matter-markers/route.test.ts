
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-markers?matter_id=${encodeURIComponent(matterId)}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-markers", () => {
  it("requires a matter_id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await GET(getReq(""))).status).toBe(400);
  });

  it("forwards the bearer token upstream and passes the answer back without it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const answer = { matter_id: "9001", loa: { status: "received", date: "2026-10-02T08:30:00Z" }, initial_ws: { status: "missing", date: "" } };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(getReq("9001"));
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(JSON.parse(text)).toEqual(answer);
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/matter-markers?matter_id=9001`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("answers from the stub with no hub configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(getReq("9002"))).json();
    expect(body.loa.status).toBe("missing");
    expect(body.initial_ws.status).toBe("missing");
    expect(body.intro.status).toBe("missing");
  });
});
