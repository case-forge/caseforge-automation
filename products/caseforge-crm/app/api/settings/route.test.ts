import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { jwtVerify } from "jose";
import { ACCESS_AUD_ENV, ACCESS_TEAM_DOMAIN_ENV } from "@/lib/accessIdentity";
import { resetStubAppSettings } from "@/lib/stubAppSettings";
import { GET, PATCH } from "./route";

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
  resetStubAppSettings();
});

const patch = (body: unknown, cookie?: string, extra: Record<string, string> = {}) =>
  new NextRequest("http://localhost/api/settings", { method: "PATCH", body: typeof body === "string" ? body : JSON.stringify(body), headers: { "Content-Type": "application/json", ...(cookie ? { cookie } : {}), ...extra } });

describe("/api/settings in stub mode", () => {
  it("lists the settings, editable by default and read-only for the non-admin cookie", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await (await GET(new NextRequest("http://localhost/api/settings"))).json()).can_edit).toBe(true);
    const other = new NextRequest("http://localhost/api/settings", { headers: { cookie: "caseforge_stub_models_admin=0" } });
    expect((await (await GET(other)).json()).can_edit).toBe(false);
  });

  it("refuses a malformed body, an empty change and a non-admin, and saves in memory", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await PATCH(patch("not json"))).status).toBe(400);
    expect((await PATCH(patch({ values: {} }))).status).toBe(400);
    expect((await PATCH(patch({ values: [1] }))).status).toBe(400);
    expect((await PATCH(patch({ values: { minutes_per_page: 99 } }))).status).toBe(422);
    expect((await PATCH(patch({ values: { minutes_per_page: 4 } }, "caseforge_stub_models_admin=0"))).status).toBe(403);
    const ok = await PATCH(patch({ values: { office_town: "Leeds" } }));
    expect(ok.status).toBe(200);
    expect(ok.headers.get("set-cookie")).toBeNull();
  });
});

describe("/api/settings forwarding", () => {
  it("sends the save to the hub with the token kept on the server and passes the plain-words refusal through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ can_edit: true, settings: [], groups: [], status: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Theme is set by the environment (CASEFORGE_SETTING_THEME_LOCK) and cannot be changed here" }), { status: 409 }));
    asDeveloper(fetchMock);

    const ok = await PATCH(patch({ values: { office_town: "Leeds" } }, undefined, SIGNED_IN));
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/settings");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ values: { office_town: "Leeds" } });

    const refused = await PATCH(patch({ values: { theme_lock: "force-light" } }, undefined, SIGNED_IN));
    expect(refused.status).toBe(409);
    expect((await refused.json()).error).toContain("CASEFORGE_SETTING_THEME_LOCK");
  });
});

describe("/api/settings is changed by a developer only", () => {
  it("refuses a save from the stub admin and worker roles, and still lets them read", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    for (const role of ["admin", "worker"]) {
      const cookie = `caseforge_stub_role=${role}`;
      expect((await PATCH(patch({ values: { office_town: "Leeds" } }, cookie))).status).toBe(403);
      expect((await GET(new NextRequest("http://localhost/api/settings", { headers: { cookie } }))).status).toBe(200);
    }
  });
});
