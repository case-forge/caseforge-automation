
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";
import { stubStatusBoard } from "@/lib/stubMilestones";

const env = (name: string): string => ["CASEFORGE", "_", name].join("");

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown) =>
  new NextRequest("http://localhost/api/wetransfer-gate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/wetransfer-gate", () => {
  it("asks for a matter before it calls the hub", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    expect((await POST(post({}))).status).toBe(400);
  });

  it("forwards only the matter id, never a name from the browser, and keeps the token on the server", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(post({ matter_id: "9009", by: "Someone Else" }));
    expect(res.status).toBe(200);
    expect(await res.text()).not.toContain("test-token");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/wetransfer-gate");
    expect(JSON.parse(init.body)).toEqual({ matter_id: "9009" });
  });

  it("passes a hub refusal back as a plain error", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Not waiting for permission." }), { status: 409 })));
    const res = await POST(post({ matter_id: "9009" }));
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("permission");
  });

  it("in stub mode answers ok and clears the pending flag on the demo board", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    const pending = () => stubStatusBoard().items.find((i) => i.matter_id === "9009")?.wetransfer_pending;
    expect(pending()).toBe(true);
    const res = await POST(post({ matter_id: "9009" }));
    expect((await res.json()).ok).toBe(true);
    expect(pending()).toBe(false);
  });
});
