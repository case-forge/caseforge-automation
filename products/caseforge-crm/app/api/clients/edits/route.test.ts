
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";

const jwtVerifyMock = vi.fn();
vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: (...args: unknown[]) => jwtVerifyMock(...args),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function stubHub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

function getReq(matterId: string): NextRequest {
  return new NextRequest(`http://localhost/api/clients/edits?matter_id=${encodeURIComponent(matterId)}`);
}

function postReq(body: unknown, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://localhost/api/clients/edits", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  jwtVerifyMock.mockClear();
});

describe("GET /api/clients/edits", () => {
  it("requires a matter_id", async () => {
    stubHub();
    const res = await GET(getReq(""));
    expect(res.status).toBe(400);
  });

  it("forwards the bearer token upstream and never to the browser", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("435"));
    const bodyText = await res.text();

    expect(res.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe(`${HUB}/client-viewer/client-edits?matter_id=435`);
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    expect(bodyText).not.toContain(TOKEN);
  });

  it("uses the in-memory stub and never calls fetch when CASEFORGE_HUB_API_STUB=1", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await GET(getReq("STUB-EMPTY"));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("POST /api/clients/edits", () => {
  it("applies immediately on the tailnet path, recorded as tailnet", async () => {
    stubHub();
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ edit_id: "e1", status: "applied" }), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", field_name: "name_last", new_value: "Cherrytest" }));

    expect(res.status).toBe(201);
    expect(jwtVerifyMock).not.toHaveBeenCalled();
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    const sentBody = JSON.parse((init.body as string) ?? "{}");
    expect(sentBody.edited_by).toBe("tailnet");
    expect(sentBody.new_value).toBe("Cherrytest");
    expect((init.headers as Record<string, string>)["X-CaseForge-Client"]).toBe("client-viewer");
    expect((init.headers as Record<string, string>)["Remote-User"]).toBeUndefined();
  });

  it("records the signed-in person and ignores a typed name in the body", async () => {
    stubHub();
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", "aud");
    jwtVerifyMock.mockResolvedValueOnce({ payload: { email: "office@example.test" } });
    const fetchSpy = vi.fn(async () =>
      new Response(JSON.stringify({ edit_id: "e1", status: "applied" }), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq(
        { matter_id: "435", field_name: "name_last", new_value: "Cherrytest", editor_name: "Somebody Else" },
        { "Cf-Access-Jwt-Assertion": "good.token.here" },
      ),
    );

    expect(res.status).toBe(201);
    const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
    expect(JSON.parse((init.body as string) ?? "{}").edited_by).toBe("office@example.test");
    expect((init.headers as Record<string, string>)["Remote-User"]).toBe("office@example.test");
  });

  it("still refuses a present-but-invalid Access JWT", async () => {
    stubHub();
    vi.stubEnv("CASEFORGE_CF_ACCESS_TEAM_DOMAIN", "example.cloudflareaccess.com");
    vi.stubEnv("CASEFORGE_CF_ACCESS_AUD", "aud");
    jwtVerifyMock.mockRejectedValueOnce(new Error("signature verification failed"));
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq(
        { matter_id: "435", field_name: "name_last", new_value: "Cherrytest" },
        { "Cf-Access-Jwt-Assertion": "bad.token.here" },
      ),
    );

    expect(res.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects a missing new_value without calling fetch", async () => {
    stubHub();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(postReq({ matter_id: "435", field_name: "name_last" }));

    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("stub mode stores and echoes back an edit without calling fetch", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq({ matter_id: "STUB-ROUTE-TEST", field_name: "name_last", new_value: "Cherrytest" }),
    );
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.field_label).toBe("Last name");
    expect(body.edited_by).toBe("tailnet");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the hub env is not configured", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const res = await POST(
      postReq({ matter_id: "435", field_name: "name_last", new_value: "Cherrytest" }),
    );

    expect(res.status).toBe(503);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("never forwards the bearer token to the browser on an upstream error", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    );

    const res = await POST(
      postReq({ matter_id: "435", field_name: "name_last", new_value: "Cherrytest" }),
    );
    const text = await res.text();

    expect(res.status).toBe(500);
    expect(text).not.toContain(TOKEN);
  });
});

describe("POST /api/clients/edits blank values and refusal reasons", () => {
  it("forwards a blank and a space-only middle name as a cleared value", async () => {
    stubHub();
    for (const value of ["", "   "]) {
      const fetchSpy = vi.fn(async () => new Response(JSON.stringify({ edit_id: "e1" }), { status: 201 }));
      vi.stubGlobal("fetch", fetchSpy);
      const res = await POST(postReq({ matter_id: "435", field_name: "name_middle", new_value: value }));
      expect(res.status).toBe(201);
      const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
      expect(JSON.parse(init.body as string).new_value).toBe("");
    }
  });

  it("shows the hub's reason when the refusal is a validation-error list", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: [{ msg: "Field required" }] }), { status: 422 })),
    );
    const res = await POST(postReq({ matter_id: "435", field_name: "name_first", new_value: "" }));
    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({ error: "Field required" });
  });

  it("shows a string reason and falls back to the generic text for anything else", async () => {
    stubHub();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "name_first cannot be blank" }), { status: 422 })),
    );
    const res = await POST(postReq({ matter_id: "435", field_name: "name_first", new_value: "" }));
    expect(await res.json()).toEqual({ error: "name_first cannot be blank" });
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 502 })));
    const res2 = await POST(postReq({ matter_id: "435", field_name: "name_first", new_value: "x" }));
    expect(await res2.json()).toEqual({ error: "upstream request failed" });
  });
});
