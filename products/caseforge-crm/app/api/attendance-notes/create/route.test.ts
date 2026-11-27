
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

vi.mock("jose", () => ({
  createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER",
  jwtVerify: vi.fn(),
}));

const HUB = "http://hub.internal:8770";
const TOKEN = "test-token-not-a-real-secret";

function hubEnv() {
  vi.stubEnv("CASEFORGE_HUB_API_URL", HUB);
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", TOKEN);
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
}

function postReq(body: unknown): NextRequest {
  return new NextRequest("http://localhost/api/attendance-notes/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("validation", () => {
  const good = { matter_id: "9001", caller: "court", attendance_folder: "CA", note_text: "Called about the hearing." };

  it.each([
    ["no matter", { ...good, matter_id: "" }],
    ["unknown caller", { ...good, caller: "solicitor" }],
    ["other without a name", { ...good, caller: "other", caller_other: "  " }],
    ["empty note", { ...good, attendance_folder: "CA", note_text: "   " }],
  ])("refuses %s without calling the hub", async (_name, body) => {
    hubEnv();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const res = await POST(postReq(body));
    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

it("sends the caller and note upstream with the bearer token, and answers as soon as it is queued", async () => {
  hubEnv();
  const fetchSpy = vi.fn(
    async () =>
      new Response(
        JSON.stringify({ draft_id: "d1", matter_id: "9001", status: "pending" }),
        { status: 202 },
      ),
  );
  vi.stubGlobal("fetch", fetchSpy);

  const res = await POST(
    postReq({ matter_id: "9001", caller: "other", caller_other: "Ms Jones", attendance_folder: "CA", note_text: "Asked about dates." }),
  );

  expect(res.status).toBe(202);
  expect((await res.json()).draft_id).toBe("d1");
  const [url, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
  expect(String(url)).toBe(`${HUB}/client-viewer/attendance-notes/create`);
  expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
  expect(JSON.parse(String(init.body))).toEqual({
    matter_id: "9001",
    caller: "other",
    caller_other: "Ms Jones",
    attendance_folder: "CA",
    note_text: "Asked about dates.",
  });
});

it("does not send a typed name for a caller that is not other", async () => {
  hubEnv();
  const fetchSpy = vi.fn(async () => new Response(JSON.stringify({}), { status: 201 }));
  vi.stubGlobal("fetch", fetchSpy);
  await POST(postReq({ matter_id: "9001", caller: "court", caller_other: "leftover", attendance_folder: "CA", note_text: "x" }));
  const [, init] = fetchSpy.mock.calls[0] as unknown as [URL, RequestInit];
  expect(JSON.parse(String(init.body)).caller_other).toBe("");
});

it("passes the hub's reason through on a 422 and never the raw body", async () => {
  hubEnv();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ detail: "matter 9001 has no live attendance-note folder yet", secret: "x" }), { status: 422 })),
  );
  const res = await POST(postReq({ matter_id: "9001", caller: "client", attendance_folder: "CA", note_text: "x" }));
  expect(res.status).toBe(422);
  expect(await res.json()).toEqual({ error: "matter 9001 has no live attendance-note folder yet" });
});

it("fails closed when the hub is not configured", async () => {
  vi.stubEnv("CASEFORGE_HUB_API_URL", "");
  vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "");
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
  const res = await POST(postReq({ matter_id: "9001", caller: "client", attendance_folder: "CA", note_text: "x" }));
  expect(res.status).toBe(503);
});

it("answers from the stub without calling fetch", async () => {
  vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  const res = await POST(postReq({ matter_id: "9001", caller: "counsel", attendance_folder: "CA", note_text: "x" }));
  expect(res.status).toBe(202);
  expect(fetchSpy).not.toHaveBeenCalled();
});

describe("time spent", () => {
  const good = { matter_id: "9001", caller: "client", attendance_folder: "CA", note_text: "Called." };

  it.each([
    ["zero", 0],
    ["over 99 hours 59 minutes", 6000],
    ["a fraction", 12.5],
    ["text", "30"],
  ])("refuses %s without calling the hub", async (_name, time_minutes) => {
    hubEnv();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const res = await POST(postReq({ ...good, time_minutes }));
    expect(res.status).toBe(400);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards whole minutes upstream, and sends nothing when none were set", async () => {
    hubEnv();
    const fetchSpy = vi.fn(async () => new Response(JSON.stringify({}), { status: 201 }));
    vi.stubGlobal("fetch", fetchSpy);
    await POST(postReq({ ...good, time_minutes: 65 }));
    await POST(postReq(good));
    const bodies = fetchSpy.mock.calls.map((c) => JSON.parse(String((c as unknown as [URL, RequestInit])[1].body)));
    expect(bodies[0].time_minutes).toBe(65);
    expect("time_minutes" in bodies[1]).toBe(false);
  });
});

describe("perusal and preparation", () => {
  const base = { matter_id: "248", caller: "respondent", attendance_folder: "CA", note_text: "perused the order" };

  function hubSpy() {
    hubEnv();
    const spy = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response(JSON.stringify({ draft_id: "d1", matter_id: "248", status: "pending" }), { status: 202 }));
    vi.stubGlobal("fetch", spy);
    return spy;
  }
  const sent = (spy: ReturnType<typeof hubSpy>) => JSON.parse(String(spy.mock.calls[0][1]?.body));

  it("forwards a perusal's kind, party, time and pages", async () => {
    const spy = hubSpy();
    const res = await POST(postReq({ ...base, kind: "perusal", time_minutes: 198, pages: 99 }));
    expect(res.status).toBe(202);
    expect(sent(spy)).toMatchObject({ kind: "perusal", caller: "respondent", time_minutes: 198, pages: 99 });
    expect(sent(spy)).not.toHaveProperty("doc_kind");
  });

  it("forwards a preparation the same way, and drops pages from a plain attendance", async () => {
    const spy = hubSpy();
    await POST(postReq({ ...base, kind: "preparation", time_minutes: 30, pages: 15 }));
    expect(sent(spy)).toMatchObject({ kind: "preparation", time_minutes: 30, pages: 15 });
    const spy2 = hubSpy();
    await POST(postReq({ ...base, time_minutes: 30, pages: 15 }));
    expect(sent(spy2)).not.toHaveProperty("pages");
  });

  it("takes a preparation with no party, and forwards the typed Other text trimmed and capped", async () => {
    const spy = hubSpy();
    expect((await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x", kind: "preparation", doc_kind: "other", doc_other: "  bank\n statement  " }))).status).toBe(202);
    expect(sent(spy)).toMatchObject({ kind: "preparation", doc_kind: "other", doc_other: "bank statement" });
    const spy2 = hubSpy();
    await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x", kind: "perusal", doc_kind: "other", doc_other: "y".repeat(300) }));
    expect(String(sent(spy2).doc_other)).toHaveLength(60);
    const spy3 = hubSpy();
    await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x", kind: "perusal", doc_kind: "order", doc_other: "ignored" }));
    expect(sent(spy3)).not.toHaveProperty("doc_other");
  });

  it("needs a party for a plain attendance", async () => {
    const spy = hubSpy();
    expect((await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x" }))).status).toBe(400);
    expect(spy).not.toHaveBeenCalled();
  });

  it("takes a perusal with a document type and no party, and drops an unknown type", async () => {
    const spy = hubSpy();
    expect((await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x", kind: "perusal", doc_kind: "order" }))).status).toBe(202);
    expect(sent(spy)).toMatchObject({ kind: "perusal", doc_kind: "order" });
    expect(sent(spy)).not.toHaveProperty("caller");
    const spy2 = hubSpy();
    await POST(postReq({ matter_id: "248", attendance_folder: "CA", note_text: "x", kind: "perusal", doc_kind: "nonsense" }));
    expect(sent(spy2)).not.toHaveProperty("doc_kind");
  });

  it("passes the chosen folder (FLA, CA or an Other name) to the hub and refuses none or both groups", async () => {
    const spy = hubSpy();
    await POST(postReq({ ...base, attendance_folder: "FLA" }));
    expect(sent(spy)).toMatchObject({ attendance_folder: "FLA" });
    const spy2 = hubSpy();
    await POST(postReq({ ...base, attendance_folder: "Mediation notes" }));
    expect(sent(spy2)).toMatchObject({ attendance_folder: "Mediation notes" });
    const none = { ...base } as Record<string, unknown>;
    delete none.attendance_folder;
    expect((await POST(postReq(none))).status).toBe(400);
    expect((await POST(postReq({ ...base, attendance_folder: "NMO CAO" }))).status).toBe(400);
  });

  it("refuses a pages value that is not a whole number from 1 to 5000", async () => {
    const spy = hubSpy();
    expect((await POST(postReq({ ...base, kind: "perusal", pages: 0 }))).status).toBe(400);
    expect((await POST(postReq({ ...base, kind: "perusal", pages: 5001 }))).status).toBe(400);
    expect(spy).not.toHaveBeenCalled();
  });

  it("refuses letter and bundle notes, which can no longer be made", async () => {
    const spy = hubSpy();
    for (const kind of ["letter_in", "letter_out", "bundle"]) {
      expect((await POST(postReq({ ...base, kind }))).status).toBe(400);
    }
    expect(spy).not.toHaveBeenCalled();
  });

  it("sends no kind for an ordinary attendance, so an older hub is unaffected", async () => {
    const spy = hubSpy();
    await POST(postReq(base));
    expect(sent(spy)).not.toHaveProperty("kind");
  });

  it("refuses an unknown kind before it reaches the hub", async () => {
    const spy = hubSpy();
    expect((await POST(postReq({ ...base, kind: "email" }))).status).toBe(400);
    expect(spy).not.toHaveBeenCalled();
  });
});
