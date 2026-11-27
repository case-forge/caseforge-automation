
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
  return new NextRequest("http://localhost/api/vergil/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function readAll(res: Response): Promise<string> {
  return res.text();
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/vergil/ask", () => {
  it("requires a question", async () => {
    stubHub();
    const res = await POST(postReq({ matter_id: "579" }));
    expect(res.status).toBe(400);
  });

  it("requires a matter_id -- gh#437, this route never serves an un-anchored conversation", async () => {
    stubHub();
    const res = await POST(postReq({ question: "hi" }));
    expect(res.status).toBe(400);
  });

  it("refuses a question over 20,000 characters with a plain 400 and never calls the hub", async () => {
    stubHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const res = await POST(postReq({ question: "x".repeat(20001), matter_id: "579" }));
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "Question is too long (max 20,000 characters). Paste a shorter extract." });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards a question of exactly 20,000 characters", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () => new Response("event: done\ndata: {}\n\n", { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    const res = await POST(postReq({ question: "x".repeat(20000), matter_id: "579" }));
    expect(res.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("forwards question/session_id/matter_id upstream and streams the body through", async () => {
    stubHub();
    const upstreamBody = "event: delta\ndata: {\"text\":\"hi\"}\n\n";
    const fetchSpy = vi.fn(
      async () =>
        new Response(upstreamBody, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq({ question: "what orders has she applied for?", matter_id: "579", session_id: "" }),
    );

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    expect(await readAll(res)).toBe(upstreamBody);

    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/vergil/ask`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    const sentBody = JSON.parse(init.body as string);
    expect(sentBody).toEqual({ question: "what orders has she applied for?", session_id: "", matter_id: "579" });
  });

  it("never forwards the bearer token to the browser", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("event: done\ndata: {}\n\n", { status: 200 })),
    );
    const res = await POST(postReq({ question: "hi", matter_id: "579" }));
    expect(await readAll(res)).not.toContain(TOKEN);
  });

  it("returns 503 when the hub is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const res = await POST(postReq({ question: "hi", matter_id: "579" }));
    expect(res.status).toBe(503);
  });

  it("mirrors the upstream failure status and never forwards its raw body", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("internal stack trace leaking secrets", { status: 500 })),
    );
    const res = await POST(postReq({ question: "hi", matter_id: "579" }));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBe("upstream request failed");
  });

  it("uses the in-memory stub stream and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ question: "what orders has she applied for?", matter_id: "579" }));
    const text = await readAll(res);

    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    expect(text).toContain("event: session");
    expect(text).toContain("event: delta");
    expect(text).toContain("event: done");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
