import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const get = (query: string) => new NextRequest(`http://localhost/api/audit-folders/link${query}`);

describe("GET /api/audit-folders/link", () => {
  it("needs a client and a path", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await GET(get("?client=A"))).status).toBe(400);
    expect((await GET(get("?path=x.pdf"))).status).toBe(400);
  });

  it("says plainly that the demo has no SharePoint", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await GET(get("?client=A&path=x.pdf"));
    expect(res.status).toBe(404);
    expect(await res.text()).toContain("demo");
  });

  it("redirects to a SharePoint link the hub made, and to nothing else", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.test");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "t");
    const answer = (url: string) => vi.fn(async () => new Response(JSON.stringify({ url }), { status: 200 }));
    vi.stubGlobal("fetch", answer("https://example.sharepoint.com/:b:/s/x/abc"));
    const ok = await GET(get("?client=A&path=x.pdf"));
    expect(ok.status).toBe(302);
    expect(ok.headers.get("location")).toBe("https://example.sharepoint.com/:b:/s/x/abc");
    vi.stubGlobal("fetch", answer("https://evil.example/phish"));
    expect((await GET(get("?client=A&path=x.pdf"))).status).toBe(502);
  });

  it("explains an item the index does not hold", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.test");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "t");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 404 })));
    const res = await GET(get("?client=A&path=x.pdf"));
    expect(res.status).toBe(404);
    expect(await res.text()).toContain("file index");
  });
});
