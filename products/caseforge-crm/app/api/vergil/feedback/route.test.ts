
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

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

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/vergil/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/vergil/feedback", () => {
  it("rejects a body that is not JSON", async () => {
    stubHub();
    expect((await POST(postReq("not json"))).status).toBe(400);
  });

  it("rejects a verdict that is not up or down", async () => {
    stubHub();
    expect((await POST(postReq({ id: "goose:s1:1", verdict: "meh" }))).status).toBe(422);
  });

  it("requires an id", async () => {
    stubHub();
    expect((await POST(postReq({ verdict: "up" }))).status).toBe(422);
  });

  it("forwards the verdict with the bearer token and never returns the token", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ id: "goose:s1:2", verdict: "down", comment: "matter:542" }));
    const text = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/retrieval/feedback`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(String(init.body))).toEqual({ id: "goose:s1:2", verdict: "down", comment: "matter:542" });
    expect(text).not.toContain(TOKEN);
  });

  it("acknowledges without calling the hub in stub mode", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const res = await POST(postReq({ id: "goose:s1:1", verdict: "up" }));
    expect(res.status).toBe(200);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect((await POST(postReq({ id: "goose:s1:1", verdict: "up" }))).status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("propagates an upstream failure status without leaking its body", async () => {
    stubHub();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("secret upstream detail", { status: 502 })));
    const res = await POST(postReq({ id: "goose:s1:1", verdict: "up" }));
    expect(res.status).toBe(502);
    expect(await res.text()).not.toContain("secret upstream detail");
  });
});
