
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const jwtVerifyMock = vi.fn();
vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: (...args: unknown[]) => jwtVerifyMock(...args),
}));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  jwtVerifyMock.mockReset();
});

type RouteModule = Record<string, unknown>;
const routes = (import.meta as unknown as { glob: (p: string) => Record<string, () => Promise<RouteModule>> }).glob("../app/api/**/route.ts");
const WRITES = ["POST", "PUT", "PATCH", "DELETE"] as const;

describe("CRM-01: a cross-site browser write is refused before any route reads it", () => {
  it("every state-changing route answers 403 or 415 to a cross-site text/plain POST", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", "");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    const accepted: string[] = [];
    for (const [file, load] of Object.entries(routes)) {
      const mod = await load();
      const path = file.replace("../app", "").replace("/route.ts", "");
      for (const method of WRITES) {
        const handler = mod[method] as ((r: NextRequest) => Promise<Response>) | undefined;
        if (!handler) continue;
        const request = new NextRequest(`http://crm.test${path}`, {
          method,
          headers: {
            "Content-Type": "text/plain",
            Origin: "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "no-cors",
          },
          body: method === "DELETE" ? undefined : '{"matter_id":"1","by":"x"}',
        });
        let status = 0;
        try {
          status = (await handler(request)).status;
        } catch {
          status = 500;
        }
        if (status !== 403 && status !== 415) accepted.push(`${method} ${path} -> ${status}`);
      }
    }
    expect(accepted, `routes that parsed a cross-site text/plain write:\n${accepted.join("\n")}`).toEqual([]);

  }, 60_000);
});

describe("CRM-03: a route that calls the hub carries the verified person with it", () => {
  const HUB = "http://hub.internal:8771";

  function arrange() {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "team.example.test");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", "aud-example");
    jwtVerifyMock.mockResolvedValue({ payload: { email: "staff@example.test", exp: 4102444800 } });
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ matter_id: "1", children: [], parties: [], ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
  }

  function remoteUserOf(fetchSpy: ReturnType<typeof vi.fn>): string | undefined {
    const init = (fetchSpy.mock.calls[0] as unknown as [unknown, RequestInit])[1];
    return (init.headers as Record<string, string>)["Remote-User"];
  }

  it("GET /api/clients/children (children's details) forwards Remote-User", async () => {
    const fetchSpy = arrange();
    const { GET } = await import("../app/api/clients/children/route");
    await GET(new NextRequest("http://crm.test/api/clients/children?matter_id=1", { headers: { "Cf-Access-Jwt-Assertion": "jwt" } }));
    expect(remoteUserOf(fetchSpy)).toBe("staff@example.test");
  });

  it("GET /api/clients/parties (respondent contact details) forwards Remote-User", async () => {
    const fetchSpy = arrange();
    const { GET } = await import("../app/api/clients/parties/route");
    await GET(new NextRequest("http://crm.test/api/clients/parties?matter_id=1", { headers: { "Cf-Access-Jwt-Assertion": "jwt" } }));
    expect(remoteUserOf(fetchSpy)).toBe("staff@example.test");
  });

  it("POST /api/attendance-notes/create (a billed write) forwards Remote-User", async () => {
    const fetchSpy = arrange();
    const { POST } = await import("../app/api/attendance-notes/create/route");
    await POST(
      new NextRequest("http://crm.test/api/attendance-notes/create", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Cf-Access-Jwt-Assertion": "jwt" },
        body: JSON.stringify({ matter_id: "1", caller: "client", attendance_folder: "CA", note_text: "Spoke to client." }),
      }),
    );
    expect(fetchSpy).toHaveBeenCalled();
    expect(remoteUserOf(fetchSpy)).toBe("staff@example.test");
  });

  it("static: no route sends the hub token without hubIdentityHeaders", async () => {
    const { readdirSync, readFileSync, statSync } = await import("node:fs");
    const { join } = await import("node:path");
    const walk = (dir: string): string[] =>
      readdirSync(dir).flatMap((name) => {
        const full = join(dir, name);
        return statSync(full).isDirectory() ? walk(full) : name === "route.ts" ? [full] : [];
      });
    const offenders = walk(join(__dirname, "..", "app", "api")).filter((file) => {
      const text = readFileSync(file, "utf8");
      return text.includes("Bearer ") && !/hubGetJson|hubPostJson|hubGetFile|hubIdentityHeaders/.test(text);
    });
    expect(offenders).toEqual([]);
  });
});

describe("CRM-10: a request that came through the Cloudflare tunnel without an Access identity is refused", () => {
  it("GET /api/clients/matter-flags with Cf-Connecting-Ip and Cf-Ray but no JWT answers 401 or 403", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "team.example.test");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", "aud-example");
    const { GET } = await import("../app/api/clients/matter-flags/route");
    const res = await GET(
      new NextRequest("http://crm.test/api/clients/matter-flags?matter_id=1", {
        headers: { "Cf-Connecting-Ip": "203.0.113.9", "Cf-Ray": "8a1b2c3d4e5f-LHR" },
      }),
    );
    expect([401, 403]).toContain(res.status);
  });
});
