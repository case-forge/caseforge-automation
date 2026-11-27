
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

const env = (name: string): string => ["CASEFORGE", "_", name].join("");

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown) => new NextRequest("http://localhost/api/nudge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/nudge", () => {
  it("asks for a matter and a known document before it calls the hub", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    expect((await POST(post({ doc: "client_docs" }))).status).toBe(400);
    expect((await POST(post({ matter_id: "9012" }))).status).toBe(400);
    expect((await POST(post({ matter_id: "9012", doc: "anything" }))).status).toBe(400);
  });

  it("forwards only the matter and the document, never a name, and keeps the token on the server", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await POST(post({ matter_id: "9012", doc: "witness_statement", by: "Someone Else", client_name: "X" }));
    expect(res.status).toBe(200);
    expect(await res.text()).not.toContain("test-token");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/nudge");
    expect(JSON.parse(init.body)).toEqual({ matter_id: "9012", doc: "witness_statement" });
  });

  it("passes the hub's refusal back as one plain line", async () => {
    vi.stubEnv(env("HUB_API_URL"), "http://hub.internal:8770");
    vi.stubEnv(env("CHAT_API_TOKEN"), "test-token-not-a-real-secret");
    vi.stubEnv(env("HUB_API_STUB"), "");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "The client has no email address." }), { status: 409 })));
    const res = await POST(post({ matter_id: "9012", doc: "client_docs" }));
    expect(res.status).toBe(409);
    expect((await res.json()).error).toContain("no email address");
  });

  it("in stub mode answers ok", async () => {
    vi.stubEnv(env("HUB_API_STUB"), "1");
    const body = await (await POST(post({ matter_id: "9012", doc: "client_docs" }))).json();
    expect(body).toMatchObject({ ok: true, matter_id: "9012", doc: "client_docs" });
  });
});
