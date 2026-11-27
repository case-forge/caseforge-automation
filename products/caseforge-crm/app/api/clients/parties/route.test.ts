
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

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

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/parties?matter_id=${encodeURIComponent(matterId)}`);
}

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/clients/parties", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("GET /api/clients/parties", () => {
  it("requires a matter_id", async () => {
    stubHub();
    const res = await GET(getReq(""));
    expect(res.status).toBe(400);
  });

  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ matter_id: "435", parties: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("435"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/parties?matter_id=435`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("uses the stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("435"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ matter_id: "435", parties: [] });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /api/clients/parties", () => {
  it("requires matter_id", async () => {
    stubHub();
    const res = await POST(postReq({ role: "Respondent" }));
    expect(res.status).toBe(400);
  });

  it("forwards a well-formed new party to the hub API", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(
        JSON.stringify({
          party_id: "1", matter_id: "435", role: "Respondent", display_name: "Sam Charlietest",
          aka_name: "", dob_iso: "", address_text: "1 Road", address_owner: "",
          phone_primary: "", phone_owner: "", email_primary: "", email_owner: "",
        }),
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq({ matter_id: "435", role: "Respondent", name_first: "Sam", name_last: "Jones", address_line1: "1 Road" }),
    );

    expect(res.status).toBe(201);
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    const sentBody = JSON.parse((init.body as string) ?? "{}");
    expect(sentBody.name_first).toBe("Sam");
    expect(sentBody.name_last).toBe("Jones");
    expect(sentBody.address_line1).toBe("1 Road");
    expect(sentBody.edited_by).toBe("tailnet");
    expect((init.headers as Record<string, string>)["X-CaseForge-Client"]).toBe("client-viewer");
  });

  it("stub mode echoes back a party without calling fetch", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", role: "Respondent" }));

    expect(res.status).toBe(201);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
