
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

const jwtVerifyMock = vi.fn();
vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: (...args: unknown[]) => jwtVerifyMock(...args),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";
const CF_TEAM_DOMAIN = "example.cloudflareaccess.com";
const CF_AUD = "023a4d53e434afde3f7b8ef94a67d2b4f64badcfcd6e24f45dea8bc9c79b0e37";

function stubAccessEnv() {
  vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", CF_TEAM_DOMAIN);
  vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", CF_AUD);
}

function req(query: string, extra = "", headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`http://localhost/api/clients/search?q=${encodeURIComponent(query)}${extra}`, {
    headers,
  });
}

function stubHub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  jwtVerifyMock.mockClear();
});

describe("GET /api/clients/search", () => {
  it("rejects a query under 2 characters without ever calling fetch", async () => {
    stubHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("a"));

    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("Dewtest"));

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(
        JSON.stringify({ query: "Dewtest", resolved_query: "Dewtest", source: "sql", count: 0, results: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("Dewtest"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/clients/search?q=Dewtest&limit=20`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("passes matter rows through unchanged, including the untyped extra.nino_canonical", async () => {
    stubHub();
    const payload = {
      query: "Dewtest",
      resolved_query: "Dewtest",
      source: "sql",
      count: 1,
      results: [
        {
          matter_id: "1",
          client_name: "Emma Dewtest",
          extra: { nino_canonical: "JK925813B" },
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );

    const res = await GET(req("Dewtest"));

    expect(await res.json()).toEqual(payload);
  });

  it("discards an upstream error body rather than forwarding it", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      async () => new Response("Server=caseforge-clientdb-internal;Database=live;", { status: 500 }),
    );

    const res = await GET(req("Dewtest"));
    const text = await res.text();

    expect(res.status).toBe(500);
    expect(text).not.toContain("caseforge-clientdb-internal");
  });

  it("returns 502 when the upstream is unreachable", async () => {
    stubHub();
    vi.stubGlobal("fetch", async () => {
      throw new Error("ECONNREFUSED");
    });

    const res = await GET(req("Dewtest"));

    expect(res.status).toBe(502);
  });

  it("uses the canned stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("anything"));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.count).toBe(6);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("stub mode's error path returns 502 without calling fetch", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("STUB_ERROR"));

    expect(res.status).toBe(502);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("Access unconfigured (tailnet path): no Remote-User header reaches the hub", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ query: "Dewtest", resolved_query: "Dewtest", source: "sql", count: 0, results: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await GET(req("Dewtest"));

    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect((init.headers as Record<string, string>)["Remote-User"]).toBeUndefined();
    expect(jwtVerifyMock).not.toHaveBeenCalled();
  });

  it("a valid JWT reaches the upstream call as Remote-User (presence-proof on the real fetch headers)", async () => {
    stubHub();
    stubAccessEnv();
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "solicitor@example.org" } });
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ query: "Dewtest", resolved_query: "Dewtest", source: "sql", count: 0, results: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await GET(
      req("Dewtest", "", {
        "Cf-Access-Jwt-Assertion": "header.payload.signature",
        "Cf-Access-Authenticated-User-Email": "solicitor@example.org",
      }),
    );

    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.org");
  });

  it("a forged inbound Remote-User is ignored -- the upstream call carries the JWT's own email", async () => {
    stubHub();
    stubAccessEnv();
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "real@example.org" } });
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ query: "Dewtest", resolved_query: "Dewtest", source: "sql", count: 0, results: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await GET(
      req("Dewtest", "", {
        "Cf-Access-Jwt-Assertion": "header.payload.signature",
        "Remote-User": "attacker@evil.example",
      }),
    );

    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("real@example.org");
  });

  it("an invalid JWT is refused with 403 before ever calling the hub", async () => {
    stubHub();
    stubAccessEnv();
    jwtVerifyMock.mockRejectedValueOnce(new Error("signature verification failed"));
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("Dewtest", "", { "Cf-Access-Jwt-Assertion": "bad.token.here" }));

    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("a bare email header without a JWT is refused with 403 (impersonation shape)", async () => {
    stubHub();
    stubAccessEnv();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("Dewtest", "", { "Cf-Access-Authenticated-User-Email": "attacker@example.com" }));

    expect(res.status).toBe(403);
    expect(jwtVerifyMock).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
