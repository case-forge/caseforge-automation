
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/status-board", () => {
  it("forwards the token upstream and passes the answer back without it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const answer = { columns: [], items: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/status-board"));
    const text = await res.text();
    expect(JSON.parse(text)).toEqual(answer);
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/status-board`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("answers from the stub with every stage column and a row per fictional client", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(new NextRequest("http://localhost/api/status-board"))).json();
    expect(body.columns.map((c: { label: string }) => c.label)).toEqual(["Contacted", "Papers signed", "Filed", "Service requested", "Served", "LAA signed", "Invoice paid", "LAA interim cert", "LAA final cert"]);
    expect(body.items.length).toBeGreaterThan(1);
    expect(Object.keys(body.items[0].milestones)).toEqual(body.columns.map((c: { key: string }) => c.key));
  });
});
