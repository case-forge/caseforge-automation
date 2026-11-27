import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const req = () => new NextRequest("http://localhost/api/scans");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/scans", () => {
  it("answers from the stub with made-up rows", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const table = await (await route.GET(req())).json();
    expect(table.readable).toBe(true);
    expect(table.rows.length).toBe(table.total);
    expect(table.rows.length).toBeGreaterThan(0);
  });

  it("is read only: the route file exports no write method", () => {
    expect(Object.keys(route).filter((name) => ["POST", "PUT", "PATCH", "DELETE"].includes(name))).toEqual([]);
  });

  it("asks the hub's scans route, keeps the token on the server and passes the table back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ folder: "F", readable: false, total: 0, folders_not_listed: 0, read_utc: "", rows: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await route.GET(req());
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/scans");
    expect(fetchMock.mock.calls[0][1].method).toBeUndefined();
    const text = await res.text();
    expect(JSON.parse(text).readable).toBe(false);
    expect(text).not.toContain("test-token-not-a-real-secret");
  });

  it("does not pass an upstream failure's body back", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("secret detail", { status: 502 })));
    const res = await route.GET(req());
    expect(res.status).toBe(502);
    expect(await res.text()).not.toContain("secret detail");
  });
});
