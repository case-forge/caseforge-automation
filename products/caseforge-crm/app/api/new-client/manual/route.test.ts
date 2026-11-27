import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const post = (body: unknown, headers: Record<string, string> = {}) =>
  new NextRequest("http://localhost/api/new-client/manual", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "application/json", ...headers } });
const base = { first_name: "A", last_name: "B", category: "crime" };

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function hub(payload: unknown = { created: true, matter_id: "7" }) {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("POST /api/new-client/manual", () => {
  it("asks for the names and matter, but not for an email", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    for (const missing of ["first_name", "last_name", "category"]) {
      const body: Record<string, string> = { ...base };
      delete body[missing];
      expect((await route.POST(post(body))).status).toBe(400);
    }
    expect((await route.POST(post(base))).status).toBe(200);
  });

  it("sends only the named fields to the hub, blanks left out, and keeps the token on the server", async () => {
    const fetchMock = hub();
    const res = await route.POST(post({ ...base, phone: " +44  7700 900123 ", evil: "x" }));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client/manual");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      ...base, by: "tailnet", address_checked: false, phone: "+44 7700 900123",
    });
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });

  it("sends a preview to the hub's preview route", async () => {
    const fetchMock = hub({ preview: true, manual: true });
    await route.POST(post({ ...base, preview: true, email: "a@b.co" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client/manual/preview");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).email).toBe("a@b.co");
  });

  it("refuses a junk phone number before the hub is called", async () => {
    const fetchMock = hub();
    expect((await route.POST(post({ ...base, phone: "call me" }))).status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes the details to the hub tidied, leaving blank ones out", async () => {
    const fetchMock = hub();
    await route.POST(post({ ...base, dob: " 20/09/1959 ", nino: "AB 12 34 56 C", address_line1: "1  Example Road", postcode: "SW1A 1AA", address_line2: "  ", matter_details: "Synthetic." }));
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(sent).toMatchObject({ dob: "20/09/1959", nino: "AB 12 34 56 C", address_line1: "1 Example Road", postcode: "SW1A 1AA", matter_details: "Synthetic." });
    expect(sent).not.toHaveProperty("address_line2");
    expect(sent).not.toHaveProperty("middle_name");
  });

  it("the stub preview shows the fuller record and makes nothing", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await route.POST(post({ ...base, preview: true, dob: "20/09/1959", address_line1: "1 Example Road", postcode: "sw1a 1aa" }));
    const body = await res.json();
    expect(body.record.people).toMatchObject({ dob_iso: "20/09/1959", address_line1: "1 Example Road", address_postcode: "SW1A 1AA" });
  });
});
