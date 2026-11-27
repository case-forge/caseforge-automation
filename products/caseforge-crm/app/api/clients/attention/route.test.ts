
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function stubHub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

function getReq(): NextRequest {
  return new NextRequest("http://localhost/api/clients/attention");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/attention", () => {
  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ configured: true, red_count: 1, yellow_count: 0, red: [], yellow: [] }),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq());
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/attention`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("passes no assignee to the hub and keeps the token on the server", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ configured: true, red_count: 0, yellow_count: 0, green_count: 0, red: [], yellow: [], green: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/clients/attention"));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/attention");
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });

  it("uses the in-memory stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq());

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      configured: true,
      red_count: 0,
      yellow_count: 0,
      green_count: 0,
      red: [],
      yellow: [],
      green: [],
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq());

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("propagates the upstream failure status without leaking its body", async () => {
    stubHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 502 })));

    const res = await GET(getReq());
    const bodyText = await res.text();

    expect(res.status).toBe(502);
    expect(bodyText).not.toContain("secret upstream detail");
  });
});
