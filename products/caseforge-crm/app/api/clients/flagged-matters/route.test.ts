import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

describe("GET /api/clients/flagged-matters", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "secret-token");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("forwards the signed-in user so the hub charges exposure to them", async () => {
    const fetchMock = vi.fn(async () => Response.json({ results: [], flags_by_matter: {} }));
    vi.stubGlobal("fetch", fetchMock);
    await GET(new NextRequest("http://localhost/api/clients/flagged-matters?flags=starred"));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(url.searchParams.get("flags")).toBe("starred");
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.invalid");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer secret-token");
  });
});
