import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "./route";
import { stubFieldReviewQueue } from "@/lib/stub";

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

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/field-review-queue", () => {
  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ results: [], flags_by_matter: {} }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(new NextRequest("http://localhost/api/clients/field-review-queue"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/field-review-queue`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("uses the stub (a non-empty queue) and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(new NextRequest("http://localhost/api/clients/field-review-queue"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(stubFieldReviewQueue());
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(new NextRequest("http://localhost/api/clients/field-review-queue"));

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("never forwards the bearer token to the browser on an upstream error", async () => {
    stubHub();
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));

    const res = await GET(new NextRequest("http://localhost/api/clients/field-review-queue"));
    const text = await res.text();

    expect(res.status).toBe(500);
    expect(text).not.toContain(TOKEN);
  });
});
