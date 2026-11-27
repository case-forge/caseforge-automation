
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

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-tasks?matter_id=${encodeURIComponent(matterId)}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-tasks", () => {
  it("requires a matter_id", async () => {
    stubHub();
    const res = await GET(getReq(""));
    expect(res.status).toBe(400);
  });

  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ matter_id: "544", configured: true, open_complaints: 1, open_updates: 0, items: [] }),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("544"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/matter-tasks?matter_id=544`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("uses the in-memory stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("544"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      matter_id: "544",
      configured: true,
      open_complaints: 0,
      open_updates: 0,
      open_settlements: 0,
      items: [],
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("544"));

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("propagates the upstream failure status without leaking its body", async () => {
    stubHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 502 })));

    const res = await GET(getReq("544"));
    const bodyText = await res.text();

    expect(res.status).toBe(502);
    expect(bodyText).not.toContain("secret upstream detail");
  });
});
