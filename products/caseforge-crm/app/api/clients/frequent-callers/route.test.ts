
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

function req(): NextRequest {
  return new NextRequest("http://localhost/api/clients/frequent-callers");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

it("forwards the bearer token upstream and never to the browser", async () => {
  stubHub();
  const fetchSpy = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          results: [{ matter_id: "435", client_name: "Cherrytest", extra: {} }],
          an_counts: { "435": 3 },
          pinned_matters: [],
        }),
        { status: 200 },
      ),
  );
  vi.stubGlobal("fetch", fetchSpy);

  const res = await GET(req());
  const bodyText = await res.text();

  expect(res.status).toBe(200);
  const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
  expect(String(url)).toBe(`${HUB}/client-viewer/frequent-callers`);
  expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  expect(bodyText).not.toContain(TOKEN);
});

it("uses the in-memory stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);

  const res = await GET(req());

  expect(res.status).toBe(200);
  expect(await res.json()).toEqual({ results: [], an_counts: {}, pinned_matters: [] });
  expect(fetchSpy).not.toHaveBeenCalled();
});

it("fails closed when the hub env is not configured", async () => {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);

  const res = await GET(req());

  expect(res.status).toBe(503);
  expect(fetchSpy).not.toHaveBeenCalled();
});
