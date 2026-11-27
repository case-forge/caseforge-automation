
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const env = (name: string): string => ["CASEFORGE", "_", name].join("");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/auto-send", () => {
  it("forwards to the hub route with the token", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/auto-send"));
    expect(await res.json()).toEqual({ items: [] });
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/auto-send");
  });

  it("passes a missing hub route through as its status", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "t");
    vi.stubEnv(env("HUB_API_STUB"), "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 404 })));
    expect((await GET(new NextRequest("http://localhost/api/auto-send"))).status).toBe(404);
  });

  it("answers from the stub with every state, one leaving within minutes", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    const body = await (await GET(new NextRequest("http://localhost/api/auto-send"))).json();
    const states = new Set(body.items.map((i: { state: string }) => i.state));
    expect([...states].sort()).toEqual(["blocked", "cancelled", "leaving_soon", "left"]);
    const soon = body.items.find((i: { state: string }) => i.state === "leaving_soon");
    expect(Date.parse(soon.leaves_utc) - Date.now()).toBeLessThan(15 * 60_000);
  });
});
