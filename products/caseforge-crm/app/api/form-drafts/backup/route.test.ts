import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

const post = (body: unknown) =>
  POST(new NextRequest("http://localhost/api/form-drafts/backup", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json" } }));

describe("/api/form-drafts/backup", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "secret-token");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("GET asks the hub for the matter's form draft as the signed-in user", async () => {
    const fetchMock = vi.fn(async () => Response.json({ saved_at: null, data: null }));
    vi.stubGlobal("fetch", fetchMock);
    await GET(new NextRequest("http://localhost/api/form-drafts/backup?matter_id=435&form_id=client-edit"));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(url.pathname).toBe("/client-viewer/form-drafts/backup");
    expect(url.searchParams.get("matter_id")).toBe("435");
    expect(url.searchParams.get("form_id")).toBe("client-edit");
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("solicitor@example.invalid");
  });

  it("POST forwards only the known fields", async () => {
    const fetchMock = vi.fn(async () => Response.json({}));
    vi.stubGlobal("fetch", fetchMock);
    await post({ matter_id: "435", form_id: "client-edit", saved_at: 5, data: { note: "x" }, extra: "dropped" });
    const [, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ matter_id: "435", form_id: "client-edit", saved_at: 5, data: { note: "x" } });
  });

  it("refuses a request missing the matter or form without calling the hub", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await GET(new NextRequest("http://localhost/api/form-drafts/backup?matter_id=435"))).status).toBe(400);
    expect((await post({ form_id: "client-edit", data: null })).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
