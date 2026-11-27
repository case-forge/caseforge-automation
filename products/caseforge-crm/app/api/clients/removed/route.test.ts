import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown) =>
  new NextRequest("http://localhost/api/clients/removed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

function hub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/clients/removed", () => {
  it("needs the typed name and a reason before it calls the hub", async () => {
    const fetchMock = hub();
    const base = { action: "remove", matter_id: "7", typed_name: "A B", reason: "Duplicate" };
    for (const patch of [{ typed_name: "" }, { reason: "" }, { matter_id: "x" }, { action: "purge" }]) {
      expect((await route.POST(post({ ...base, ...patch }))).status).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a removal to the hub's remove route with only the named fields", async () => {
    const fetchMock = hub();
    const res = await route.POST(
      post({ action: "remove", matter_id: "7", typed_name: "A B", reason: "Duplicate", evil: "x" }),
    );
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/clients/remove");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ matter_id: "7", typed_name: "A B", reason: "Duplicate", by: "tailnet" });
  });

  it("sends an undo to the hub's undo route", async () => {
    const fetchMock = hub();
    await route.POST(post({ action: "undo", matter_id: "7" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/clients/undo-remove");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ matter_id: "7", by: "tailnet" });
  });
});
