
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { stubCreateHearing, stubResetHearings } from "@/lib/stub";
import { POST as vacatePost } from "./vacate/route";
import { POST as requestPost } from "./request/route";
import { GET as optionsGet } from "./request-options/route";
import { POST as decisionPost } from "./court-decision/route";

vi.mock("@/lib/accessIdentity", () => ({
  resolveIdentityForRoute: vi.fn(async () => ({ remoteUser: "solicitor@example.invalid", rejection: null })),
}));

function post(path: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
  stubResetHearings();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("vacate route", () => {
  it("refuses a bad kind, a move with no date, and a replacement on a non-move", async () => {
    expect((await vacatePost(post("/api/hearings/vacate", { hearing_id: 1, kind: "banana" }))).status).toBe(400);
    expect((await vacatePost(post("/api/hearings/vacate", { hearing_id: 1, kind: "moved" }))).status).toBe(400);
    expect(
      (await vacatePost(post("/api/hearings/vacate", { hearing_id: 1, kind: "no_longer_acting", replacement: { hearing_date: "2026-10-02" } }))).status,
    ).toBe(400);
  });

  it("moves a hearing in the demo store: old vacated, new created", async () => {
    const h = stubCreateHearing({ case_ref: "ZZ26F00002", hearing_date: "2026-09-25", hearing_time: "10:00", court: "Example Family Court" }, "Sam");
    const res = await vacatePost(post("/api/hearings/vacate", { hearing_id: h.hearing_id, kind: "moved", replacement: { hearing_date: "2026-09-25", hearing_time: "14:00" } }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.hearing.status).toBe("vacated");
    expect(body.replacement.hearing_time).toBe("14:00");
  });
});

describe("request and court decision routes", () => {
  it("needs a kind and at least one reason", async () => {
    expect((await requestPost(post("/api/hearings/request", { hearing_id: 1, kind: "sent", reasons: ["x"] }))).status).toBe(400);
    expect((await requestPost(post("/api/hearings/request", { hearing_id: 1, kind: "vacation", reasons: [" "] }))).status).toBe(400);
    expect((await requestPost(post("/api/hearings/request", { hearing_id: 1, kind: "vacation", reasons: ["x"], form: "C100" }))).status).toBe(400);
    expect((await decisionPost(post("/api/hearings/court-decision", { hearing_id: 1, agreed: "yes" }))).status).toBe(400);
  });

  it("goes red on request and clears on refusal, in the demo store", async () => {
    const h = stubCreateHearing({ case_ref: "ZZ26F00003", hearing_date: "2026-09-25", hearing_time: "10:00", order_types: "CAO" }, "Sam");
    const options = await (await optionsGet(new NextRequest(`http://localhost/api/hearings/request-options?hearing_id=${h.hearing_id}`))).json();
    expect(options.form).toBe("C2");
    const asked = await requestPost(post("/api/hearings/request", { hearing_id: h.hearing_id, kind: "vacation", reasons: ["No counsel available."] }));
    expect(asked.status).toBe(200);
    expect((await asked.json()).hearing.request_state).toBe("vacation_requested");
    const refused = await decisionPost(post("/api/hearings/court-decision", { hearing_id: h.hearing_id, agreed: false }));
    expect((await refused.json()).hearing.request_state).toBe("");
  });
});

describe("real path", () => {
  it("forwards a request to the hub with the token and never returns it", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ hearing: { hearing_id: 1 }, form: "FP2", draft: null, summary: "ok" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const res = await requestPost(post("/api/hearings/request", { hearing_id: 1, kind: "hybrid", reasons: ["Remote."], draft: false }));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toBe("http://hub.internal:8770/client-viewer/hearings/request");
    expect(JSON.parse(String(init.body))).toMatchObject({ hearing_id: 1, kind: "hybrid", draft: false });
    expect(await res.text()).not.toContain("test-token");
  });
});
