
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "alex@example.test", rejection: null })),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function req(query: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-neighbour?${query}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-neighbour", () => {
  it("refuses a missing or non-numeric matter, or a bad direction", async () => {
    expect((await GET(req("dir=next"))).status).toBe(400);
    expect((await GET(req("matter_id=abc&dir=next"))).status).toBe(400);
    expect((await GET(req("matter_id=5&dir=up"))).status).toBe(400);
  });

  it("forwards to the hub with the identity and the token, and passes the answer back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ matter_id: "511" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(req("matter_id=510&dir=next"));
    const text = await res.text();
    expect(JSON.parse(text)).toEqual({ matter_id: "511" });
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/matter-neighbour?matter_id=510&dir=next`);
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TOKEN}`);
    expect(headers["Remote-User"]).toBe("alex@example.test");
    expect(headers["X-CaseForge-Client"]).toBe("client-viewer");
  });

  it("answers from the stub clients in stub mode", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const body = await (await GET(req("matter_id=9001&dir=prev"))).json();
    expect(body).toEqual({ matter_id: null });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
