import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const createRemoteJWKSetMock = vi.fn((_url: URL, _opts?: unknown) => "FAKE_JWKS_RESOLVER");
const jwtVerifyMock = vi.fn();

vi.mock("jose", () => ({
  createRemoteJWKSet: (...args: [URL, unknown?]) => createRemoteJWKSetMock(...args),
  jwtVerify: (...args: unknown[]) => jwtVerifyMock(...args),
}));

const TEAM_DOMAIN = "example.cloudflareaccess.com";
const AUD = "b176b8eb69d9f0c9a3c1e074b94b5e5dae21a2b98ec11e3e39f6b986fb9a7cf2";

function headersWith(values: Record<string, string>): Headers {
  return new Headers(values);
}

async function loadModule() {
  vi.resetModules();
  return import("./accessIdentity");
}

beforeEach(() => {
  createRemoteJWKSetMock.mockClear();
  jwtVerifyMock.mockClear();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("resolveAccessIdentity - Access not configured (env unset)", () => {
  it("resolves absent and never touches jose, even with a JWT header present", async () => {
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({ "Cf-Access-Jwt-Assertion": "whatever.looks.like-a-jwt" }),
    );

    expect(result).toEqual({ kind: "absent" });
    expect(createRemoteJWKSetMock).not.toHaveBeenCalled();
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("resolves absent with no headers at all", async () => {
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(headersWith({}));

    expect(result).toEqual({ kind: "absent" });
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("resolves absent when only one of the two env vars is set", async () => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);

    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({ "Cf-Access-Jwt-Assertion": "whatever.looks.like-a-jwt" }),
    );

    expect(result).toEqual({ kind: "absent" });
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("stays silent for a genuinely unset pair - no warning noise on the default CI/tailnet shape", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { resolveAccessIdentity } = await loadModule();

    await resolveAccessIdentity(headersWith({}));

    expect(warnSpy).not.toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it("warns when an env var is present but empty - a misconfigured deploy, not a deliberate unset", async () => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(headersWith({}));

    expect(result).toEqual({ kind: "absent" });
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0]?.join(" ")).toContain("present but empty");
    warnSpy.mockRestore();
  });
});

describe("resolveAccessIdentity - Access configured", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
  });

  it("resolves absent when no Access headers are present (tailnet/stub shape)", async () => {
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(headersWith({}));

    expect(result).toEqual({ kind: "absent" });
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("resolves identified with the JWT's own email claim on a valid token", async () => {
    jwtVerifyMock.mockResolvedValueOnce({
      payload: { email: "solicitor@example.org", aud: [AUD], iss: `https://${TEAM_DOMAIN}` },
    });
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({
        "Cf-Access-Jwt-Assertion": "header.payload.signature",
        "Cf-Access-Authenticated-User-Email": "solicitor@example.org",
      }),
    );

    expect(result).toEqual({ kind: "identified", email: "solicitor@example.org" });
    expect(jwtVerifyMock).toHaveBeenCalledTimes(1);
    const [jwtArg, , optionsArg] = jwtVerifyMock.mock.calls[0] as [string, unknown, Record<string, unknown>];
    expect(jwtArg).toBe("header.payload.signature");
    expect(optionsArg.issuer).toBe(`https://${TEAM_DOMAIN}`);
    expect(optionsArg.audience).toBe(AUD);
    expect(optionsArg.algorithms).toEqual(["RS256"]);
  });

  it("builds the JWKS resolver from the configured team domain", async () => {
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "a@example.org" } });
    const { resolveAccessIdentity } = await loadModule();

    await resolveAccessIdentity(headersWith({ "Cf-Access-Jwt-Assertion": "a.b.c" }));

    expect(createRemoteJWKSetMock).toHaveBeenCalledTimes(1);
    const [urlArg] = createRemoteJWKSetMock.mock.calls[0] as [URL];
    expect(urlArg.toString()).toBe(`https://${TEAM_DOMAIN}/cdn-cgi/access/certs`);
  });

  it("reuses the cached JWKS resolver across multiple calls in the same process", async () => {
    jwtVerifyMock.mockResolvedValue({ payload: { email: "a@example.org" } });
    const { resolveAccessIdentity } = await loadModule();

    await resolveAccessIdentity(headersWith({ "Cf-Access-Jwt-Assertion": "a.b.c" }));
    await resolveAccessIdentity(headersWith({ "Cf-Access-Jwt-Assertion": "d.e.f" }));

    expect(createRemoteJWKSetMock).toHaveBeenCalledTimes(1);
    expect(jwtVerifyMock).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["bad signature", new Error("signature verification failed")],
    ["wrong audience", new Error("unexpected \"aud\" claim value")],
    ["wrong issuer", new Error("unexpected \"iss\" claim value")],
    ["expired", new Error('"exp" claim timestamp check failed')],
    ["JWKS unreachable", new Error("request timed out")],
  ])("rejects on %s and never resolves an email", async (_label, thrown) => {
    jwtVerifyMock.mockRejectedValueOnce(thrown);
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({ "Cf-Access-Jwt-Assertion": "header.payload.signature" }),
    );

    expect(result.kind).toBe("rejected");
    expect(result).not.toHaveProperty("email");
  });

  it("rejects a validated token that carries no usable email claim", async () => {
    jwtVerifyMock.mockResolvedValueOnce({ payload: { sub: "user-123" } });
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({ "Cf-Access-Jwt-Assertion": "header.payload.signature" }),
    );

    expect(result.kind).toBe("rejected");
  });

  it("rejects a bare Cf-Access-Authenticated-User-Email header with no JWT behind it", async () => {
    const { resolveAccessIdentity } = await loadModule();

    const result = await resolveAccessIdentity(
      headersWith({ "Cf-Access-Authenticated-User-Email": "attacker@example.com" }),
    );

    expect(result).toEqual({
      kind: "rejected",
      reason: "email header present without a JWT assertion",
    });
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("never logs the raw JWT value when rejecting", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    jwtVerifyMock.mockRejectedValueOnce(new Error("signature verification failed"));
    const secretJwt = "SUPER-SECRET-JWT-VALUE-do-not-log.payload.signature";
    const { resolveAccessIdentity } = await loadModule();

    await resolveAccessIdentity(headersWith({ "Cf-Access-Jwt-Assertion": secretJwt }));

    for (const call of warnSpy.mock.calls) {
      expect(call.join(" ")).not.toContain(secretJwt);
    }
    warnSpy.mockRestore();
  });
});

describe("resolveIdentityForRoute", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
  });

  it("returns remoteUser and no rejection for a valid JWT", async () => {
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "solicitor@example.org" } });
    const { resolveIdentityForRoute } = await loadModule();

    const outcome = await resolveIdentityForRoute(
      headersWith({ "Cf-Access-Jwt-Assertion": "a.b.c" }),
    );

    expect(outcome.rejection).toBeNull();
    expect(outcome.remoteUser).toBe("solicitor@example.org");
  });

  it("returns a 403 rejection Response for an invalid JWT, with a generic body", async () => {
    jwtVerifyMock.mockRejectedValueOnce(new Error("signature verification failed"));
    const { resolveIdentityForRoute } = await loadModule();

    const outcome = await resolveIdentityForRoute(
      headersWith({ "Cf-Access-Jwt-Assertion": "a.b.c" }),
    );

    expect(outcome.remoteUser).toBeNull();
    expect(outcome.rejection).not.toBeNull();
    expect(outcome.rejection?.status).toBe(403);
    const body = await outcome.rejection?.json();
    expect(body).toEqual({ error: "identity verification failed" });
  });

  it("returns null remoteUser and no rejection when no Access headers are present", async () => {
    const { resolveIdentityForRoute } = await loadModule();

    const outcome = await resolveIdentityForRoute(headersWith({}));

    expect(outcome.rejection).toBeNull();
    expect(outcome.remoteUser).toBeNull();
  });
});

describe("refused identity timing", () => {
  it("logs a refused identity with the route from the proxy header", async () => {
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", TEAM_DOMAIN);
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", AUD);
    jwtVerifyMock.mockRejectedValueOnce(new Error("bad signature"));
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const { resolveIdentityForRoute } = await loadModule();
    const headers = headersWith({ "Cf-Access-Jwt-Assertion": "not.a.jwt", "x-caseforge-api-route": "/api/today" });
    const { rejection } = await resolveIdentityForRoute(headers);
    expect(rejection?.status).toBe(403);
    expect(rejection?.headers.get("Server-Timing")).toContain("identity;dur=");
    expect(String(info.mock.calls.at(-1)?.[0])).toContain("route=/api/today status=403");
    info.mockRestore();
  });
});
