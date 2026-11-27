import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/pulse", () => {
  it("answers every part from the stub with no hub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await GET(new NextRequest("http://localhost/api/pulse"))).json();
    expect(Object.keys(body).sort()).toEqual(["attention", "errors", "flag_counts", "notifications", "pending_new_clients", "robot_notices", "statement_replies"]);
    expect(body.attention).not.toHaveProperty("assignee");
  });

  it("keeps the token on the server and passes the answer back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ attention: null, errors: ["attention"] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/pulse"));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/pulse");
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });
});
