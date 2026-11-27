
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function stubHub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

function getReq(query: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-summary?${query}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-summary", () => {
  it("requires a matter_id and known parts", async () => {
    stubHub();
    expect((await GET(getReq("matter_id="))).status).toBe(400);
    expect((await GET(getReq("matter_id=542&parts=flags,nonsense"))).status).toBe(400);
  });

  it("forwards the parts and the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ matter_id: "542", errors: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("matter_id=542&parts=flags,person_matters"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/matter-summary?matter_id=542&parts=flags%2Cperson_matters`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("answers each asked part from the stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("matter_id=542&parts=flags,person_matters"));

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(Object.keys(body).sort()).toEqual(["errors", "flags", "matter_id", "person_matters"]);
    expect(body.person_matters).toEqual({ matter_id: "542", matters: [] });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("propagates the upstream failure status without leaking its body", async () => {
    stubHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 500 })));

    const res = await GET(getReq("matter_id=542"));

    expect(res.status).toBe(500);
    expect(await res.text()).not.toContain("secret upstream detail");
  });
});
