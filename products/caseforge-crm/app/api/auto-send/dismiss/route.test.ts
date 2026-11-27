
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { stubAutoSend } from "@/lib/stubAutoSend";

const env = (name: string): string => ["CASEFORGE", "_", name].join("");

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown) =>
  new NextRequest("http://localhost/api/auto-send/dismiss", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/auto-send/dismiss", () => {
  it("asks for an id before it calls the hub", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    expect((await POST(post({}))).status).toBe(400);
  });

  it("forwards only the id, never a name from the browser, and keeps the token on the server", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(post({ id: "as-4", by: "Someone Else" }));
    expect(res.status).toBe(200);
    expect(await res.text()).not.toContain("test-token");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/auto-send/dismiss");
    expect(JSON.parse(init.body)).toEqual({ id: "as-4" });
  });

  it("passes a hub refusal back as a plain error", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not a cancelled row." }), { status: 409 })));
    const res = await POST(post({ id: "as-1" }));
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("cancelled");
  });

  it("in stub mode answers ok and the demo list no longer holds the row", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    const cancelled = stubAutoSend().items.find((i) => i.state === "cancelled")!;
    expect((await (await POST(post({ id: cancelled.id }))).json()).ok).toBe(true);
    expect(stubAutoSend().items.some((i) => i.id === cancelled.id)).toBe(false);
  });
});
