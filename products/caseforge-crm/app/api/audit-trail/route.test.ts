import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/audit-trail", () => {
  it("answers from the stub, honouring kind and search", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const people = await (await GET(new NextRequest("http://localhost/api/audit-trail?kind=person"))).json();
    expect(people.rows.length).toBeGreaterThan(0);
    expect(people.rows.every((r: { kind: string }) => r.kind === "person")).toBe(true);
    const agents = await (await GET(new NextRequest("http://localhost/api/audit-trail?kind=agent"))).json();
    expect(agents.kind).toBe("agent");
    const found = await (await GET(new NextRequest("http://localhost/api/audit-trail?q=casework-scans"))).json();
    expect(found.total).toBe(1);
    const odd = await (await GET(new NextRequest("http://localhost/api/audit-trail?kind=everyone"))).json();
    expect(odd.kind).toBe("all");
  });

  it("forwards only the four known parameters to the hub, keeps the token on the server, and passes a 403 through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ rows: [], total: 0 }))).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Admins only" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    const ok = await GET(new NextRequest("http://localhost/api/audit-trail?kind=person&days=30&q=intro&limit=50&offset=100&evil=1&days2=x"));
    expect(ok.status).toBe(200);
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.origin + url.pathname).toBe("http://hub.internal:8770/client-viewer/audit-trail");
    expect(Object.fromEntries(url.searchParams)).toEqual({ kind: "person", days: "30", limit: "50", offset: "100", q: "intro" });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(await ok.text()).not.toContain("test-token-not-a-real-secret");

    const refused = await GET(new NextRequest("http://localhost/api/audit-trail"));
    expect(refused.status).toBe(403);
  });

  it("drops a day, limit or offset that is not a plain number", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "t");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await GET(new NextRequest("http://localhost/api/audit-trail?days=7;drop&limit=-1&offset=1e9"));
    expect(Object.fromEntries(new URL(String(fetchMock.mock.calls[0][0])).searchParams)).toEqual({ kind: "all" });
  });
});
