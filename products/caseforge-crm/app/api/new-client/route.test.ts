import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown) =>
  new NextRequest("http://localhost/api/new-client", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/new-client", () => {
  it("asks for every field before it calls the hub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    for (const missing of ["first_name", "last_name", "email", "category"]) {
      const body: Record<string, string> = { first_name: "A", last_name: "B", email: "a@b.co", category: "crime" };
      delete body[missing];
      expect((await route.POST(post(body))).status).toBe(400);
    }
  });

  it("sends only the named fields to the hub and keeps the token on the server", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ matter_id: "7", drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await route.POST(
      post({ first_name: "A", last_name: "B", email: "a@b.co", category: "crime", send_rif: true, send_laif: true, evil: "x" }),
    );
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client");
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent).toEqual({ first_name: "A", last_name: "B", email: "a@b.co", category: "crime", send_rif: true, send_laif: true, address_checked: false, by: "tailnet" });
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });

  it("sends the press id on a Create so a retry finishes its own press, and never on a preview", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ matter_id: "", drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const base = { first_name: "A", last_name: "B", email: "a@b.co", category: "crime", request_id: "press-1" };
    await route.POST(post(base));
    await route.POST(post({ ...base, preview: true }));
    await route.POST(post({ ...base, request_id: "x".repeat(100) }));
    const [create, preview, long] = fetchMock.mock.calls.map((call) => JSON.parse(call[1].body));
    expect(create.request_id).toBe("press-1");
    expect(preview).not.toHaveProperty("request_id");
    expect(long.request_id).toHaveLength(64);
  });

  it("sends each extra-form tick on its own, and anything but a literal true as not ticked", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ matter_id: "7", drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const base = { first_name: "A", last_name: "B", email: "a@b.co", category: "crime" };
    await route.POST(post({ ...base, send_laif: true }));
    await route.POST(post({ ...base, send_rif: "yes", send_laif: 1 }));
    const [laifOnly, neither] = fetchMock.mock.calls.map((call) => JSON.parse(call[1].body));
    expect([laifOnly.send_rif, laifOnly.send_laif]).toEqual([false, true]);
    expect([neither.send_rif, neither.send_laif]).toEqual([false, false]);
  });

  it("in stub mode, each ticked form is its own envelope in the one draft", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const base = { first_name: "A", last_name: "B", email: "a@b.co", category: "crime", preview: true };
    const both = await (await route.POST(post({ ...base, send_rif: true, send_laif: true }))).json();
    expect(both.envelopes.map((e: { documents: string }) => e.documents)).toEqual([
      "New Client Form + Letter of Authority",
      "Opponent Info Form",
      "Legal Aid Info Form",
    ]);
    expect(both.drafts).toHaveLength(1);
    const none = await (await route.POST(post(base))).json();
    expect(none.envelopes).toHaveLength(1);
    expect(none.drafts).toEqual([{ documents: "New Client Form + Letter of Authority", to: "a@b.co", subject: "stub" }]);
  });

  it("carries an optional phone number to the hub, tidied, and sends none when it is blank", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ matter_id: "", drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const base = { first_name: "A", last_name: "B", email: "a@b.co", category: "crime" };
    expect((await route.POST(post({ ...base, phone: " +44  7700 900123 " }))).status).toBe(200);
    expect((await route.POST(post({ ...base, phone: "  " }))).status).toBe(200);
    const [withPhone, blank] = fetchMock.mock.calls.map((call) => JSON.parse(call[1].body));
    expect(withPhone.phone).toBe("+44 7700 900123");
    expect(blank).not.toHaveProperty("phone");
  });

  it("refuses a junk phone number before the hub is called", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await route.POST(post({ first_name: "A", last_name: "B", email: "a@b.co", category: "crime", phone: "call me" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends a preview to the hub's preview route", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ preview: true, drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await route.POST(
      post({ first_name: "A", last_name: "B", email: "a@b.co", category: "crime", preview: true }),
    );
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client/preview");
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent).not.toHaveProperty("preview");
  });

  it("treats anything but a literal true as not a preview", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ matter_id: "7", drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    await route.POST(post({ first_name: "A", last_name: "B", email: "a@b.co", category: "crime", preview: "1" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty("is_test");
  });
});
