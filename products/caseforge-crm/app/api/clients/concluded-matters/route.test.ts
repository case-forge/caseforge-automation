import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";
const req = (query: string) => new NextRequest(`http://localhost/api/clients/concluded-matters${query}`);

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/concluded-matters", () => {
  it("answers from the stub a page at a time", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(req("?limit=50&offset=50"))).json();
    expect(body.results).toHaveLength(50);
    expect(body.next_offset).toBe(100);
  });

  it("forwards a clamped limit and offset with the token kept on the server", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ results: [], total: 0, next_offset: null })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(req("?limit=99999&offset=-5"));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/concluded-matters?limit=200&offset=0`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(await res.text()).not.toContain(TOKEN);
  });
});
