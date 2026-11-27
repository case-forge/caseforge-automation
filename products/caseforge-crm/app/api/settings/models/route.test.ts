import { afterEach, describe, expect, it, vi } from "vitest";
import { jwtVerify } from "jose";
import { NextRequest } from "next/server";
import { resetStubModelRoles } from "@/lib/stubModelRoles";
import { DELETE, GET, PUT } from "./route";
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
  resetStubModelRoles();
});

const put = (body: unknown, cookie?: string, extra: Record<string, string> = {}) =>
  new NextRequest("http://localhost/api/settings/models", { method: "PUT", body: typeof body === "string" ? body : JSON.stringify(body), headers: { "Content-Type": "application/json", ...(cookie ? { cookie } : {}), ...extra } });

describe("/api/settings/models in stub mode", () => {
  it("lists the roles, editable by default and read-only for the non-admin cookie", async () => {
    vi.stubEnv(HUB_STUB_ENV, "1");
    expect((await (await GET(new NextRequest("http://localhost/api/settings/models"))).json()).can_edit).toBe(true);
    const other = new NextRequest("http://localhost/api/settings/models", { headers: { cookie: "caseforge_stub_models_admin=0" } });
    expect((await (await GET(other)).json()).can_edit).toBe(false);
  });

  it("rejects a malformed body, free text and a non-admin before changing anything", async () => {
    vi.stubEnv(HUB_STUB_ENV, "1");
    expect((await PUT(put("not json"))).status).toBe(400);
    expect((await PUT(put({ role: "../x", model: "a/b" }))).status).toBe(400);
    expect((await PUT(put({ role: "case_summary", model: "two words" }))).status).toBe(400);
    expect((await PUT(put({ role: "case_summary", model: "free/text" }))).status).toBe(422);
    expect((await PUT(put({ role: "case_summary", model: "anthropic/claude-haiku-5.5" }, "caseforge_stub_models_admin=0"))).status).toBe(403);
    expect((await DELETE(new NextRequest("http://localhost/api/settings/models?role=bad%20role", { method: "DELETE" }))).status).toBe(400);
  });
});

function asDeveloper(rest: (url: unknown, init?: RequestInit) => unknown, role = "dev") {
  return vi.fn((url: unknown, init?: RequestInit) =>
    String(url).endsWith("/client-viewer/role") ? Promise.resolve(new Response(JSON.stringify({ role }))) : rest(url, init),
  );
}

describe("/api/settings/models is dev mode only", () => {
  it("refuses an administrator, and a worker, on every method before the hub is asked for models", async () => {
    vi.stubEnv(HUB_URL_ENV, "http://hub.internal:8770");
    vi.stubEnv(HUB_TOKEN_ENV, "test-token-not-a-real-secret");
    vi.stubEnv(HUB_STUB_ENV, "");
    for (const role of ["admin", "worker"]) {
      const rest = vi.fn();
      vi.stubGlobal("fetch", asDeveloper(rest, role));
      expect((await GET(new NextRequest("http://localhost/api/settings/models", { headers: signedIn() }))).status).toBe(403);
      expect((await PUT(put({ role: "case_summary", model: "c/d" }, undefined, signedIn()))).status).toBe(403);
      expect((await DELETE(new NextRequest("http://localhost/api/settings/models?role=case_summary", { method: "DELETE", headers: signedIn() }))).status).toBe(403);
      expect(rest).not.toHaveBeenCalled();
    }
  });

  it("refuses the stub admin role too", async () => {
    vi.stubEnv(HUB_STUB_ENV, "1");
    const admin = new NextRequest("http://localhost/api/settings/models", { headers: { cookie: "caseforge_stub_role=admin" } });
    expect((await GET(admin)).status).toBe(403);
  });
});

describe("/api/settings/models forwarding", () => {
  it("sends the admin write to the hub with the token kept on the server and passes the plain-words refusal through", async () => {
    vi.stubEnv(HUB_URL_ENV, "http://hub.internal:8770");
    vi.stubEnv(HUB_TOKEN_ENV, "test-token-not-a-real-secret");
    vi.stubEnv(HUB_STUB_ENV, "");
    const hubMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ role: "case_summary", old: "a/b", new: "c/d" })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Only a developer can change a model" }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ role: "case_summary", old: "c/d", new: "a/b" })));
    const fetchMock = hubMock;
    vi.stubGlobal("fetch", asDeveloper(hubMock));
    const person = signedIn();

    const ok = await PUT(put({ role: "case_summary", model: "c/d", expected_old: "a/b" }, undefined, person));
    expect(ok.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/settings/models/case_summary");
    expect(fetchMock.mock.calls[0][1].method).toBe("PUT");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ model: "c/d", expected_old: "a/b" });

    const refused = await PUT(put({ role: "case_summary", model: "c/d" }, undefined, person));
    expect(refused.status).toBe(403);
    expect((await refused.json()).error).toBe("Only a developer can change a model");

    const reset = await DELETE(new NextRequest("http://localhost/api/settings/models?role=case_summary", { method: "DELETE", headers: person }));
    expect(reset.status).toBe(200);
    expect(fetchMock.mock.calls[2][1].method).toBe("DELETE");
    expect(fetchMock.mock.calls[2][1].body).toBeUndefined();
  });
});
