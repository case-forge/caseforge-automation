import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { NextRequest } from "next/server";
import * as route from "../app/api/clients/nearest/route";
import { httpsOnly, miles } from "./nearest";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("nearest court and chambers", () => {
  it("formats distances and offers only https links", () => {
    expect(miles(1.234)).toBe("1.2 miles");
    expect(miles(null)).toBe("");
    expect(httpsOnly("https://c.example")).toBe("https://c.example");
    expect(httpsOnly("javascript:alert(1)")).toBeNull();
  });

  it("says nearest, never your court, and renders no HTML", () => {
    const source = readFileSync(fileURLToPath(new URL("../components/NearestHelp.tsx", import.meta.url)), "utf8");
    expect(source).toContain("Nearest court");
    expect(source.toLowerCase()).not.toContain("your court");
    expect(source).not.toContain("dangerouslySetInnerHTML");
  });

  it("asks the hub's read-only route for a matter number only", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    expect((await route.GET(new NextRequest("http://localhost/api/clients/nearest?matter_id=x"))).status).toBe(400);
    await route.GET(new NextRequest("http://localhost/api/clients/nearest?matter_id=9601"));
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect([url.pathname, url.searchParams.get("matter_id")]).toEqual(["/client-viewer/nearest", "9601"]);
  });
});
