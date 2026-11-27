import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/audit-folders", () => {
  it("answers the client list from the stub, and a tree for a known client", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const list = await (await GET(new NextRequest("http://localhost/api/audit-folders"))).json();
    expect(list.folder).toBeNull();
    expect(list.clients.length).toBeGreaterThan(1);
    const tree = await (await GET(new NextRequest("http://localhost/api/audit-folders?folder=Sample%20Client&days=30"))).json();
    expect(tree.days).toBe(30);
    expect(tree.folder.name).toBe("Sample Client");
    expect(tree.folder.items.some((i: { created: { kind: string } | null }) => i.created?.kind === "automation")).toBe(true);
  });

  it("forwards only the folder and the days, keeps the token on the server, and passes a 403 through", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ clients: [], folder: null }))).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Admins only" }), { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);

    const ok = await GET(new NextRequest("http://localhost/api/audit-folders?folder=Client%20One&days=45&evil=1&offset=9"));
    expect(ok.status).toBe(200);
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.origin + url.pathname).toBe("http://hub.internal:8770/client-viewer/audit-folders");
    expect(Object.fromEntries(url.searchParams)).toEqual({ days: "45", folder: "Client One" });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer test-token-not-a-real-secret");
    expect(await ok.text()).not.toContain("test-token-not-a-real-secret");

    const refused = await GET(new NextRequest("http://localhost/api/audit-folders"));
    expect(refused.status).toBe(403);
  });

  it("keeps the window to 1 to 90 days and falls back to 90 for anything that is not a plain number", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "t");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response("{}")));
    vi.stubGlobal("fetch", fetchMock);
    for (const days of ["7;drop", "-1", "1e9", "400", "0"]) await GET(new NextRequest(`http://localhost/api/audit-folders?days=${encodeURIComponent(days)}`));
    const seen = fetchMock.mock.calls.map((c) => new URL(String(c[0])).searchParams.get("days"));
    expect(seen).toEqual(["90", "90", "90", "90", "1"]);
  });
});
