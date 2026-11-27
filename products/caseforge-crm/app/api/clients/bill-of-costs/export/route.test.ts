
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/bill-of-costs/export?matter_id=${encodeURIComponent(matterId)}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/bill-of-costs/export", () => {
  it("requires a matter_id", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    expect((await GET(getReq(""))).status).toBe(400);
  });

  it("answers from the stub as a CSV download", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await GET(getReq("9001"));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toContain("text/csv");
    expect(res.headers.get("content-disposition")).toContain('attachment; filename="Bill-of-Costs-');
  });

  it("passes the hub's CSV and file name through, keeping the token upstream", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("TEST PERSON,Date\r\n", {
        status: 200,
        headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="Bill-of-Costs-PERSON.csv"' },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(getReq("9001"));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="Bill-of-Costs-PERSON.csv"');
    const text = await res.text();
    expect(text).toContain("TEST PERSON");
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/billing/export.csv?matter_id=9001`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it("does not pass an upstream failure's body back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("secret detail", { status: 422 })));
    const res = await GET(getReq("9001"));
    expect(res.status).toBe(422);
    expect(await res.text()).not.toContain("secret detail");
  });
});
