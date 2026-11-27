import { afterEach, describe, expect, it, vi } from "vitest";
import { jwtVerify } from "jose";
import { NextRequest } from "next/server";
import { GET } from "./route";
import { HUB_STUB_ENV, HUB_TOKEN_ENV, HUB_URL_ENV } from "@/lib/hubProxy";
import { ACCESS_AUD_ENV, ACCESS_TEAM_DOMAIN_ENV } from "@/lib/accessIdentity";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

function signedIn(): Record<string, string> {
  vi.stubEnv(ACCESS_TEAM_DOMAIN_ENV, "team.example.cloudflareaccess.com");
  vi.stubEnv(ACCESS_AUD_ENV, "aud-example");
  vi.mocked(jwtVerify).mockResolvedValue({ payload: { email: "person@example.test" } } as never);
  return { "Cf-Access-Jwt-Assertion": "valid.jwt.value" };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function hubAnswering(role: string, rest: (url: unknown, init?: RequestInit) => unknown) {
  return vi.fn((url: unknown, init?: RequestInit) =>
    String(url).endsWith("/client-viewer/role") ? Promise.resolve(new Response(JSON.stringify({ role }))) : rest(url, init),
  );
}

function live() {
  vi.stubEnv(HUB_URL_ENV, "http://hub.internal:8770");
  vi.stubEnv(HUB_TOKEN_ENV, "test-token-not-a-real-secret");
  vi.stubEnv(HUB_STUB_ENV, "");
}

describe("GET /api/system-status is dev mode only", () => {
  it("refuses an administrator and a worker without asking the hub for the boxes", async () => {
    live();
    for (const role of ["admin", "worker", "something-else"]) {
      const rest = vi.fn();
      vi.stubGlobal("fetch", hubAnswering(role, rest));
      expect((await GET(new NextRequest("http://localhost/api/system-status", { headers: signedIn() }))).status).toBe(403);
      expect(rest).not.toHaveBeenCalled();
    }
  });

  it("forwards a developer to the hub", async () => {
    live();
    const rest = vi.fn().mockResolvedValue(new Response(JSON.stringify({ boxes: [] })));
    vi.stubGlobal("fetch", hubAnswering("dev", rest));
    const res = await GET(new NextRequest("http://localhost/api/system-status", { headers: signedIn() }));
    expect(res.status).toBe(200);
    expect(String(rest.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/system-status");
  });

  it("in stub mode follows the role cookie, a developer by default", async () => {
    vi.stubEnv(HUB_STUB_ENV, "1");
    expect((await GET(new NextRequest("http://localhost/api/system-status"))).status).toBe(200);
    const admin = new NextRequest("http://localhost/api/system-status", { headers: { cookie: "caseforge_stub_role=admin" } });
    expect((await GET(admin)).status).toBe(403);
  });
});
