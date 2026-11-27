
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

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

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/matter-flags?matter_id=${encodeURIComponent(matterId)}`);
}

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/clients/matter-flags", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/matter-flags", () => {
  it("requires a matter_id", async () => {
    stubHub();
    const res = await GET(getReq(""));
    expect(res.status).toBe(400);
  });

  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(
      async () => new Response(JSON.stringify({ matter_id: "435", flags: {} }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("435"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/matter-flags?matter_id=435`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("uses the in-memory stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("STUB-EMPTY-FLAGS"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ matter_id: "STUB-EMPTY-FLAGS", flags: {}, reasons: {}, shared: {}, personal: {}, personal_reasons: {} });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /api/clients/matter-flags", () => {
  it("requires no Access identity", async () => {
    stubHub();
    const fetchSpy = vi.fn(
      async () =>
        new Response(JSON.stringify({ matter_id: "435", flags: { persistent_caller: true } }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", flag_name: "persistent_caller", is_set: true, set_by: "Somebody Else" }));

    expect(res.status).toBe(200);
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];

    expect(JSON.parse(String(init.body)).set_by).toBe("tailnet");
    expect((init.headers as Record<string, string>)["X-CaseForge-Client"]).toBe("client-viewer");
  });

  it("rejects a non-boolean is_set without calling fetch", async () => {
    stubHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", flag_name: "persistent_caller", is_set: "yes" }));

    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("stub mode stores and echoes back the flag state without calling fetch", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq({ matter_id: "STUB-FLAG-ROUTE-TEST", flag_name: "persistent_caller", is_set: true }),
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.flags).toEqual({ persistent_caller: true });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", flag_name: "persistent_caller", is_set: true }));

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("flag reasons", () => {
  it("forwards a rule's reason and only_if_reason to the hub, and nothing when they are absent", async () => {
    stubHub();
    const fetchSpy = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response(JSON.stringify({ matter_id: "601", flags: {}, reasons: {} }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    await POST(postReq({ matter_id: "601", flag_name: "flagged", is_set: true, reason: "Unfinished draft" }));
    await POST(postReq({ matter_id: "601", flag_name: "flagged", is_set: false, only_if_reason: "Unfinished draft" }));
    await POST(postReq({ matter_id: "601", flag_name: "flagged", is_set: true }));

    const bodies = fetchSpy.mock.calls.map((call) => JSON.parse(String(call[1]?.body)));
    expect(bodies[0]).toMatchObject({ reason: "Unfinished draft" });
    expect(bodies[0]).not.toHaveProperty("only_if_reason");
    expect(bodies[1]).toMatchObject({ is_set: false, only_if_reason: "Unfinished draft" });
    expect(bodies[2]).not.toHaveProperty("reason");
  });

  it("in stub mode a person's flag is their own with the reason they typed, apart from an automatic one", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const reason = "Chase the court";
    const post = async (matter: string, body: Record<string, unknown>) =>
      (await POST(postReq({ matter_id: matter, flag_name: "flagged", ...body }))).json();

    const own = await post("STUB-R1", { is_set: true, reason });
    expect(own.personal).toEqual({ flagged: true });
    expect(own.personal_reasons).toEqual({ flagged: reason });
    expect(own.shared).toEqual({});
    expect((await post("STUB-R1", { is_set: false })).flags.flagged).toBeUndefined();
  });

});
