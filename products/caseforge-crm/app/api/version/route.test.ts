
import { afterEach, describe, expect, it, vi } from "vitest";

const jwtVerifyMock = vi.fn();
vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: (...args: unknown[]) => jwtVerifyMock(...args),
}));

const TEAM_DOMAIN = "example.cloudflareaccess.com";
const AUD = "023a4d53e434afde3f7b8ef94a67d2b4f64badcfcd6e24f45dea8bc9c79b0e37";

afterEach(() => {
  vi.unstubAllEnvs();
  jwtVerifyMock.mockClear();
});

describe("GET /api/version", () => {
  it("reports sessionExpiresAt (ms) from a verified JWT's exp claim (seconds)", async () => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
    const expSeconds = 1_800_000_000;
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "solicitor@example.org", exp: expSeconds } });
    const { GET } = await import("./route");

    const res = await GET(
      new Request("http://localhost/api/version", { headers: { "Cf-Access-Jwt-Assertion": "a.b.c" } }),
    );
    const body = await res.json();

    expect(body.sessionExpiresAt).toBe(expSeconds * 1000);
    expect(typeof body.buildId).toBe("string");
  });

  it("reports null sessionExpiresAt when Access isn't in front of the request (tailnet-direct)", async () => {
    const { GET } = await import("./route");

    const res = await GET(new Request("http://localhost/api/version"));
    const body = await res.json();

    expect(body.sessionExpiresAt).toBeNull();
  });

  it("reports null sessionExpiresAt when the JWT fails verification", async () => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
    jwtVerifyMock.mockRejectedValueOnce(new Error('"exp" claim timestamp check failed'));
    const { GET } = await import("./route");

    const res = await GET(
      new Request("http://localhost/api/version", { headers: { "Cf-Access-Jwt-Assertion": "a.b.c" } }),
    );
    const body = await res.json();

    expect(body.sessionExpiresAt).toBeNull();
  });

  it("never throws when .next/BUILD_ID is absent (dev server) -- empty buildId is a real result", async () => {
    const { GET } = await import("./route");

    const res = await GET(new Request("http://localhost/api/version"));

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(typeof body.buildId).toBe("string");
  });

  it("reports commit from <dist>/COMMIT, honouring the dist dir, and null when absent or unknown", async () => {
    const { mkdtempSync, mkdirSync, writeFileSync, rmSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const nodePath = await import("node:path");
    const dir = mkdtempSync(nodePath.join(tmpdir(), "ver-"));
    const cwd = vi.spyOn(process, "cwd").mockReturnValue(dir);
    try {
      mkdirSync(nodePath.join(dir, ".next-demo"));
      const sha = "a".repeat(40);
      writeFileSync(nodePath.join(dir, ".next-demo", "COMMIT"), `${sha}\n`);
      vi.stubEnv("CASEFORGE_BUILD_DIST_DIR", ".next-demo");
      const { GET } = await import("./route");
      expect((await (await GET(new Request("http://localhost/api/version"))).json()).commit).toBe(sha);

      writeFileSync(nodePath.join(dir, ".next-demo", "COMMIT"), "unknown\n");
      expect((await (await GET(new Request("http://localhost/api/version"))).json()).commit).toBeNull();

      vi.stubEnv("CASEFORGE_BUILD_DIST_DIR", "");
      expect((await (await GET(new Request("http://localhost/api/version"))).json()).commit).toBeNull();
    } finally {
      cwd.mockRestore();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
