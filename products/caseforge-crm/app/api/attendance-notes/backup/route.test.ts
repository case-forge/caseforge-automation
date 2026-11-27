import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

const HUB = "http://hub.internal:8770";
const post = (body: unknown) =>
  POST(new NextRequest("http://localhost/api/attendance-notes/backup", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }));

describe("/api/attendance-notes/backup", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "secret-token");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("GET asks the hub for the matter's copy as the signed-in user", async () => {
    const fetchMock = vi.fn(async () => Response.json({ working: null, drafts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await GET(new NextRequest("http://localhost/api/attendance-notes/backup?matter_id=435"));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(url.pathname).toBe("/client-viewer/attendance-notes/backup");
    expect(url.searchParams.get("matter_id")).toBe("435");
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.invalid");
  });

  it("POST forwards only the matter, the working copy and the drafts", async () => {
    const fetchMock = vi.fn(async () => Response.json({ working: null, drafts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await post({ matter_id: "435", working: { noteText: "x" }, drafts: [], extra: "dropped" });
    const [, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ matter_id: "435", working: { noteText: "x" }, drafts: [] });
  });

  it("refuses a request with no matter without calling the hub", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await GET(new NextRequest("http://localhost/api/attendance-notes/backup"))).status).toBe(400);
    expect((await post({ working: null, drafts: [] })).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers from the stub without touching the network", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await (await GET(new NextRequest("http://localhost/api/attendance-notes/backup?matter_id=1"))).json()).toEqual({ working: null, drafts: [] });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
