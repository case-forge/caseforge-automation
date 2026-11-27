import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import * as route from "./route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

function hub() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const post = (body: unknown) => new NextRequest("http://localhost/api/mail-review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("/api/mail-review", () => {
  it("reads the list and one item through the hub", async () => {
    const fetchMock = hub();
    await route.GET(new NextRequest("http://localhost/api/mail-review"));
    await route.GET(new NextRequest("http://localhost/api/mail-review?n=3"));
    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe("/client-viewer/mail-review");
    const item = new URL(String(fetchMock.mock.calls[1][0]));
    expect([item.pathname, item.searchParams.get("n")]).toEqual(["/client-viewer/mail-review/item", "3"]);
    expect((await route.GET(new NextRequest("http://localhost/api/mail-review?n=x"))).status).toBe(400);
  });

  it("sends only the answer fields", async () => {
    const fetchMock = hub();
    await route.POST(post({ action: "answer", n: 3, route: "r", also: "", no_clean_answer: true, matter: "m", logic: "l", evil: "x" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/mail-review/answer");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ n: 3, route: "r", also: "", no_clean_answer: true, matter: "m", logic: "l" });
  });

  it("extends by 7 or 30 days only, under the signed-in name", async () => {
    const fetchMock = hub();
    expect((await route.POST(post({ action: "extend", days: 365 }))).status).toBe(400);
    await route.POST(post({ action: "extend", days: 30 }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/mail-review/extend");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ days: 30, by: "tailnet" });
  });

  it("gives a control email back to the hub when the prompt is closed", async () => {
    const fetchMock = hub();
    expect((await route.POST(post({ action: "control_release", job_id: "" }))).status).toBe(400);
    await route.POST(post({ action: "control_release", job_id: "j1", evil: 1 }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/mail-review/control/release");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ job_id: "j1" });
  });

  it("reads the two tabs through the hub and checks the numbers first", async () => {
    const fetchMock = hub();
    await route.GET(new NextRequest("http://localhost/api/mail-review?view=decide&offset=2"));
    await route.GET(new NextRequest("http://localhost/api/mail-review?view=control"));
    await route.GET(new NextRequest("http://localhost/api/mail-review?view=control&n=3"));
    const decide = new URL(String(fetchMock.mock.calls[0][0]));
    expect([decide.pathname, decide.searchParams.get("offset")]).toEqual(["/client-viewer/mail-review/decide", "2"]);
    expect(new URL(String(fetchMock.mock.calls[1][0])).pathname).toBe("/client-viewer/mail-review/control");
    expect(new URL(String(fetchMock.mock.calls[2][0])).searchParams.get("n")).toBe("3");
    await route.GET(new NextRequest("http://localhost/api/mail-review?view=review-batch"));
    await route.GET(new NextRequest("http://localhost/api/mail-review?view=batch"));
    expect(new URL(String(fetchMock.mock.calls[1][0])).searchParams.get("pool")).toBe("control");
    expect(new URL(String(fetchMock.mock.calls[3][0])).searchParams.get("pool")).toBe("review");
    expect(new URL(String(fetchMock.mock.calls[3][0])).pathname).toBe("/client-viewer/mail-review/control");
    expect(new URL(String(fetchMock.mock.calls[4][0])).searchParams.get("pool")).toBeNull();
    expect((await route.GET(new NextRequest("http://localhost/api/mail-review?view=other"))).status).toBe(400);
    expect((await route.GET(new NextRequest("http://localhost/api/mail-review?view=decide&offset=x"))).status).toBe(400);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("sends only the decision fields, and refuses an empty one", async () => {
    const fetchMock = hub();
    expect((await route.POST(post({ action: "decide", job_id: " " }))).status).toBe(400);
    await route.POST(post({ action: "decide", job_id: "j1", route: "Court", also: "", no_clean_answer: false, logic: "l", evil: "x" }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/mail-review/decide");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ job_id: "j1", route: "Court", also: "", logic: "l", other_text: "" });
  });

  it("passes the typed destination for Other to the hub", async () => {
    const fetchMock = hub();
    await route.POST(post({ action: "decide", job_id: "j1", route: "Other", other_text: "Social worker" }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ route: "Other", other_text: "Social worker" });
  });

  it("sends only the control fields, with a known verdict and a real date", async () => {
    const fetchMock = hub();
    expect((await route.POST(post({ action: "control", job_id: "j1", verdict: "maybe", date: "2026-10-25" }))).status).toBe(400);
    expect((await route.POST(post({ action: "control", job_id: "j1", verdict: "agree", date: "yesterday" }))).status).toBe(400);
    expect((await route.POST(post({ action: "control", job_id: "", verdict: "agree", date: "2026-10-25" }))).status).toBe(400);
    await route.POST(post({ action: "control", job_id: "j1", verdict: "disagree", route: "Junk", date: "2026-10-25", evil: 1 }));
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/mail-review/control");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ date: "2026-10-25", job_id: "j1", verdict: "disagree", route: "Junk", also: "", logic: "", other_text: "" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("serves synthetic fixtures in stub mode and still refuses the old sheet", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const control = await (await route.GET(new NextRequest("http://localhost/api/mail-review?view=control"))).json();
    expect(control.total).toBeGreaterThan(0);
    const unsure = await (await route.GET(new NextRequest("http://localhost/api/mail-review?view=review-batch"))).json();
    expect(unsure.total).toBeGreaterThan(0);
    expect(unsure.item.pool).toBe("review");
    expect(control.item.pool).toBe("control");
    expect((await route.GET(new NextRequest("http://localhost/api/mail-review"))).status).toBe(404);
  });
});
