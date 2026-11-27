
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";
const call = (qs: string) => GET(new NextRequest(`http://localhost/api/billing/daily-totals${qs}`));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/billing/daily-totals", () => {
  it("forwards the range with the token and passes the answer back without it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const answer = { days: [] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(answer), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await call("?start=2026-10-01&end=2026-10-07");
    const text = await res.text();
    expect(JSON.parse(text)).toEqual(answer);
    expect(text).not.toContain(TOKEN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe(`${HUB}/client-viewer/billing/daily-totals?start=2026-10-01&end=2026-10-07`);
    expect(init.headers.Authorization).toBe(`Bearer ${TOKEN}`);
  });

  it.each(["?start=2026-10-05&end=2026-10-01", "?start=x&end=2026-10-01", "?start=2024-01-01&end=2026-10-01"])("refuses %s without asking the hub", async (qs) => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await call(qs)).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers from the stub with one row per day, zero days included", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const body = await (await call("?start=2026-10-01&end=2026-10-07")).json();
    expect(body.days).toHaveLength(7);
    expect(body.days.some((d: { items: number }) => d.items === 0)).toBe(true);
  });

  it("passes a hub failure on as an error, not as data", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 502 })));
    expect((await call("?start=2026-10-01&end=2026-10-02")).status).toBe(502);
  });
});
