
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { GET } from "../route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function post(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/clients/attention/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/clients/attention/complete", () => {
  it("forwards the id and the signed-in name (tailnet here, a typed one ignored) upstream with the bearer token, and never returns the token", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(post({ task_id: "a:12", by: "Sam" }));
    const text = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/attention/complete`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(JSON.parse(String(init.body))).toMatchObject({ task_id: "a:12", by: "tailnet" });
    expect(text).not.toContain(TOKEN);
  });

  it("refuses a missing id and a malformed body before any hub call", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    expect((await POST(post({}))).status).toBe(400);
    expect((await POST(post("{not json"))).status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("answers ok in stub mode without calling fetch, and the demo item then leaves the stub answer", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    vi.stubEnv("CASEFORGE_STUB_ATTENTION_DEMO", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const before = await (await GET(new NextRequest("http://localhost/api/clients/attention"))).json();
    expect(before.scope_creep.map((i: { task_id: string }) => i.task_id)).toContain("a:21");
    expect(before.scope_creep_count).toBe(1);

    const res = await POST(post({ task_id: "a:21" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });

    const after = await (await GET(new NextRequest("http://localhost/api/clients/attention"))).json();
    expect(after.scope_creep).toEqual([]);
    expect(after.scope_creep_count).toBe(0);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
