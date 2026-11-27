import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

const HUB = "http://hub.internal:8770";
const call = (query: string) => GET(new NextRequest(`http://localhost/api/clients/matter-flags/batch${query}`));

describe("GET /api/clients/matter-flags/batch", () => {
  beforeEach(() => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "secret-token");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("makes one hub request for all the matters", async () => {
    const fetchMock = vi.fn(async () => Response.json({ flags_by_matter: { "1": {}, "2": { transferred: true } } }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await call("?matter_ids=1,2");
    expect(await res.json()).toEqual({ flags_by_matter: { "1": {}, "2": { transferred: true } } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0] as unknown as [URL];
    expect(url.pathname).toBe("/client-viewer/matter-flags/batch");
    expect(url.searchParams.get("matter_ids")).toBe("1,2");
  });

  it("rejects an empty or oversized list without calling the hub", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect((await call("")).status).toBe(400);
    expect((await call(`?matter_ids=${Array.from({ length: 201 }, (_, n) => n).join(",")}`)).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers from the stub without touching the network", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const body = await (await call("?matter_ids=STUB-001")).json();
    expect(Object.keys(body.flags_by_matter)).toEqual(["STUB-001"]);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
