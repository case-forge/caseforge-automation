import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { jwtVerify } from "jose";
import { ACCESS_AUD_ENV, ACCESS_TEAM_DOMAIN_ENV } from "@/lib/accessIdentity";
import { resetStubEmailClassifier } from "@/lib/stubEmailClassifier";
import { GET, PUT } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

function asDeveloper(rest: (url: unknown, init?: RequestInit) => unknown) {
  vi.stubEnv(ACCESS_TEAM_DOMAIN_ENV, "team.example.cloudflareaccess.com");
  vi.stubEnv(ACCESS_AUD_ENV, "aud-example");
  vi.mocked(jwtVerify).mockResolvedValue({ payload: { email: "person@example.test" } } as never);
  vi.stubGlobal("fetch", vi.fn((url: unknown, init?: RequestInit) => (String(url).endsWith("/client-viewer/role") ? Promise.resolve(new Response(JSON.stringify({ role: "dev" }))) : rest(url, init))));
}
const SIGNED_IN = { "Cf-Access-Jwt-Assertion": "valid.jwt.value" };

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  resetStubEmailClassifier();
});

const put = (body: unknown, cookie?: string, extra: Record<string, string> = {}) =>
  new NextRequest("http://localhost/api/settings/email-classifier", {
    method: "PUT",
    body: typeof body === "string" ? body : JSON.stringify(body),
    headers: { "Content-Type": "application/json", ...(cookie ? { cookie } : {}), ...extra },
  });

describe("/api/settings/email-classifier in stub mode", () => {
  it("lists the canned lists and keeps an added entry", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const first = await (await GET(new NextRequest("http://localhost/api/settings/email-classifier"))).json();
    expect(first.lists.court_domains.default).toContain("court.example");
    const saved = await PUT(put({ add: { court_domains: ["own.example"] }, remove: { gp_keywords: ["repeat prescription"] } }));
    expect(saved.status).toBe(200);
    const view = await saved.json();
    expect(view.lists.court_domains.effective).toContain("own.example");
    expect(view.lists.gp_keywords.effective).not.toContain("repeat prescription");
  });

  it("refuses a malformed body, an unknown list and a non-admin", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await PUT(put("not json"))).status).toBe(400);
    expect((await PUT(put({ add: { court_domains: [1] } }))).status).toBe(400);
    expect((await PUT(put({ add: { nonsense: ["x"] } }))).status).toBe(422);
    expect((await PUT(put({ add: {} }, "caseforge_stub_models_admin=0"))).status).toBe(403);
  });
});

describe("/api/settings/email-classifier forwarding", () => {
  it("sends the save to the hub with the token kept on the server and passes the refusal through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ lists: {}, audit: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Too long" }), { status: 422 }));
    asDeveloper(fetchMock);

    const ok = await PUT(put({ add: { court_domains: ["own.example"] }, remove: {} }, undefined, SIGNED_IN));
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/settings/email-classifier");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ add: { court_domains: ["own.example"] }, remove: {} });

    const refused = await PUT(put({ add: {}, remove: {} }, undefined, SIGNED_IN));
    expect(refused.status).toBe(422);
    expect((await refused.json()).error).toBe("Too long");
  });
});
