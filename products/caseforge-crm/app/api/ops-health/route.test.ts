import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function stubRequest(state?: string): NextRequest {
  return new NextRequest("http://localhost/api/ops-health", state ? { headers: { cookie: `caseforge_stub_ops_health=${state}` } } : {});
}

describe("GET /api/ops-health", () => {
  it("serves each stub state from the cookie, amber by default", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await (await GET(stubRequest())).json()).overall_severity).toBe("amber");
    expect((await (await GET(stubRequest("clear"))).json()).alerts).toEqual([]);
    expect((await (await GET(stubRequest("red"))).json()).overall_severity).toBe("red");
    expect((await (await GET(stubRequest("stale"))).json()).stale).toBe(true);
    expect((await (await GET(stubRequest("none"))).json()).available).toBe(false);
    expect((await GET(stubRequest("nonadmin"))).status).toBe(403);
  });

  it("forwards to the hub with the token kept on the server, and passes a 403 through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ available: true, alerts: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Admins only" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    const ok = await GET(new NextRequest("http://localhost/api/ops-health"));
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/ops-health");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(await ok.text()).not.toContain("test-token-not-a-real-secret");

    const refused = await GET(new NextRequest("http://localhost/api/ops-health"));
    expect(refused.status).toBe(403);
    expect(await refused.text()).not.toContain("alerts");
  });
});
