import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";
import * as removed from "../removed/route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

function hub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const post = (url: string, body: unknown) => new NextRequest(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("/api/clients/merge", () => {
  it("previews through the hub's read-only route", async () => {
    const fetchMock = hub();
    await route.GET(new NextRequest("http://localhost/api/clients/merge?from=613&into=617"));
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.pathname).toBe("/client-viewer/clients/merge-preview");
    expect(url.searchParams.get("from_matter_id")).toBe("613");
    expect(url.searchParams.get("into_matter_id")).toBe("617");
  });

  it("needs both typed names and a reason before it merges, recorded under the signed-in person", async () => {
    const fetchMock = hub();
    const base = { from_matter_id: "1", into_matter_id: "2", typed_from: "A", typed_into: "B", reason: "Duplicate" };
    for (const patch of [{ typed_from: "" }, { typed_into: "" }, { reason: "" }, { into_matter_id: "x" }]) {
      expect((await route.POST(post("http://localhost/api/clients/merge", { ...base, ...patch }))).status).toBe(400);
    }
    expect(fetchMock).not.toHaveBeenCalled();
    await route.POST(post("http://localhost/api/clients/merge", { ...base, evil: "x" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/clients/merge");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ ...base, by: "tailnet" });
  });

  it("passes the per-field choices to the hub, strings only", async () => {
    const fetchMock = hub();
    const base = { from_matter_id: "1", into_matter_id: "2", typed_from: "A", typed_into: "B", reason: "Duplicate" };
    await route.POST(post("http://localhost/api/clients/merge", { ...base, choices: { "people.dob_iso": "a", bad: 5 } }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ ...base, by: "tailnet", choices: { "people.dob_iso": "a" } });
  });

  it("undoes a merge through the hub's undo-merge route", async () => {
    const fetchMock = hub();
    await removed.POST(post("http://localhost/api/clients/removed", { action: "undo-merge", matter_id: "613" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/clients/undo-merge");
  });
});
