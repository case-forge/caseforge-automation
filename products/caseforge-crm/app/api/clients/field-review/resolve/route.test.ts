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
  return new NextRequest("http://localhost/api/clients/field-review/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/clients/field-review/resolve", () => {
  it("requires review_id", async () => {
    stubHub();
    const res = await POST(postReq({}));
    expect(res.status).toBe(400);
  });

  it("forwards to the hub API and never leaks the token", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(
        JSON.stringify({
          review_id: "r1", matter_id: "435", client_name: "", field_name: "address", field_label: "Address",
          value_snapshot: "", note: "", flagged_by: "Sam", flagged_at: "2026-09-23T00:00:00Z",
          resolved_by: "Rose", resolved_at: "2026-09-23T01:00:00Z",
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ review_id: "r1" }));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    expect(bodyText).not.toContain(TOKEN);
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(String(init.body)).resolved_by).toBe("tailnet");
  });

  it("stub mode echoes back a resolved flag without calling fetch", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ review_id: "r1" }));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.resolved_by).toBe("tailnet");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ review_id: "r1" }));

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
