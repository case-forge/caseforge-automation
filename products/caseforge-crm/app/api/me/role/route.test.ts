import { afterEach, describe, expect, it, vi } from "vitest";
import { jwtVerify } from "jose";
import { GET } from "./route";
import { loadCrmRole, parseRole } from "@/lib/devMode";
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

function live() {
  vi.stubEnv(HUB_URL_ENV, "http://hub.internal:8770");
  vi.stubEnv(HUB_TOKEN_ENV, "test-token-not-a-real-secret");
  vi.stubEnv(HUB_STUB_ENV, "");
}

describe("GET /api/me/role", () => {
  it("passes the hub's answer through, with the token kept on the server", async () => {
    live();
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "dev" })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new Request("http://localhost/api/me/role", { headers: signedIn() }));
    expect(await res.json()).toEqual({ role: "dev" });
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/role");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
  });

  it("fails closed: a refusal, an outage, a strange answer or no hub is a worker", async () => {
    live();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 500 })));
    expect(await (await GET(new Request("http://localhost/api/me/role"))).json()).toEqual({ role: "worker" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect(await (await GET(new Request("http://localhost/api/me/role"))).json()).toEqual({ role: "worker" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "superuser" }))));
    expect(await (await GET(new Request("http://localhost/api/me/role"))).json()).toEqual({ role: "worker" });
    vi.stubEnv(HUB_URL_ENV, "");
    expect(await (await GET(new Request("http://localhost/api/me/role"))).json()).toEqual({ role: "worker" });
  });

  it("parses roles and reads them in the browser", async () => {
    expect(parseRole("dev")).toBe("dev");
    expect(parseRole("admin")).toBe("admin");
    expect(parseRole(undefined)).toBe("worker");
    expect(await loadCrmRole(vi.fn().mockResolvedValue(new Response(JSON.stringify({ role: "admin" }))))).toBe("admin");
    expect(await loadCrmRole(vi.fn().mockResolvedValue(new Response("", { status: 403 })))).toBe("worker");
  });
});
