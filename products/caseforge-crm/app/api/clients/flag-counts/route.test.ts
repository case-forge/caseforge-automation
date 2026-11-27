import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

const HUB = "http://hub.internal:8770";

describe("GET /api/clients/flag-counts", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "secret-token");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("asks the hub for counts as the signed-in user and returns them", async () => {
    const fetchMock = vi.fn(async () => Response.json({ counts: { flagged: 3, starred: 1 } }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/clients/flag-counts"));
    expect(await res.json()).toEqual({ counts: { flagged: 3, starred: 1 } });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(url.toString()).toBe(`${HUB}/client-viewer/flag-counts?flags=flagged%2Cstarred`);
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.invalid");
  });

  it("returns zero counts in stub mode without touching the network", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await GET(new NextRequest("http://localhost/api/clients/flag-counts"));
    expect(await res.json()).toEqual({ counts: { flagged: 0, starred: 0 } });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not echo an upstream failure body", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("internal traceback", { status: 500 })));
    const res = await GET(new NextRequest("http://localhost/api/clients/flag-counts"));
    expect(res.status).toBe(500);
    expect(JSON.stringify(await res.json())).not.toContain("traceback");
  });
});
