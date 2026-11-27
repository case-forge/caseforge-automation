import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { NextRequest } from "next/server";
import {
  emailStateLabel,
  formsBackLabel,
  isUnfinished,
  newPressId,
  pendingBadgeLabel,
  pendingCountsStore,
  resumedLines,
  unfinishedLabel,
  waitedLabel,
  waitLine,
  waitTone,
} from "./pendingNewClients";
import { pulseStore } from "./pulse";
import * as listRoute from "../app/api/new-client/pending/route";
import * as cancelRoute from "../app/api/new-client/pending/cancel/route";
import * as resumeRoute from "../app/api/new-client/pending/resume/route";
import * as newClientRoute from "../app/api/new-client/route";
import * as pulseRoute from "../app/api/pulse/route";

vi.mock("jose", () => ({ createRemoteJWKSet: () => "FAKE_JWKS_RESOLVER", jwtVerify: vi.fn() }));

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("how long an unsent pack has waited", () => {
  const unsent = { email_state: "draft" as const, stage: "done" as const };
  it("is calm under 30 minutes, late from 30, overdue from 60, and never for a sent pack", () => {
    expect(waitTone({ ...unsent, waiting_minutes: 29 })).toBe("normal");
    expect(waitTone({ ...unsent, waiting_minutes: 30 })).toBe("late");
    expect(waitTone({ ...unsent, waiting_minutes: 60 })).toBe("overdue");
    expect(waitTone({ ...unsent, waiting_minutes: 5, overdue: true })).toBe("overdue");
    expect(waitTone({ email_state: "sent", stage: "done", waiting_minutes: 600, overdue: false })).toBe("normal");
    expect(waitTone({ email_state: "sent", stage: "pack", waiting_minutes: 61 })).toBe("overdue");
  });

  it("says it in words, not colour alone", () => {
    expect(waitedLabel(34)).toBe("34 min");
    expect(waitedLabel(65)).toBe("1 h 5 min");
    expect(waitedLabel(26 * 60)).toBe("1 d 2 h");
    expect(waitLine({ ...unsent, waiting_minutes: 10 })).toBe("");
    expect(waitLine({ ...unsent, waiting_minutes: 34 })).toContain("Waiting 34 min");
    expect(waitLine({ ...unsent, waiting_minutes: 90 })).toMatch(/^Overdue: .*1 h 30 min/);
    expect(pendingBadgeLabel(3, 3, 1)).toContain(", 1 overdue");
    expect(pendingBadgeLabel(3, 3)).not.toContain("overdue");
  });
});

describe("the new client button's badge", () => {
  it("says the count in words", () => {
    expect(pendingBadgeLabel(0)).toBe("New client");
    expect(pendingBadgeLabel(1)).toBe("New client, 1 waiting for their New Client Form");
    expect(pendingBadgeLabel(2, 1)).toBe("New client, 2 waiting for their New Client Form, 1 pack email not sent yet");
    expect(pendingBadgeLabel(3, 2)).toContain("2 pack emails not sent yet");
  });

  it("reads its numbers from the pulse, so it adds no poll of its own", () => {
    pulseStore.set({ pending_new_clients: { unsent: 2, waiting: 3 } });
    expect(pendingCountsStore.getSnapshot()).toEqual({ unsent: 2, waiting: 3 });
    pulseStore.set({ pending_new_clients: { unsent: 0, waiting: 1 } });
    expect(pendingCountsStore.getSnapshot()).toEqual({ unsent: 0, waiting: 1 });
    expect(read("./pendingNewClients.ts")).toContain("createPulseSlice");
    expect(read("./pendingNewClients.ts")).not.toContain("createPolledStore");
  });

  it("counts everyone waiting (sent or not) with the shared attention badge, in the button and its overflow entry", () => {
    const src = read("../components/NewClientButton.tsx");
    expect(src).toMatch(/\{waiting > 0 && \(\s*<span className="attention-count" aria-hidden="true">\s*\{waiting\}/);
    expect(src).toContain('className="cf-btn cf-btn--flush attention-button attention-button--newclient"');
    expect(src).toContain("aria-label={pendingBadgeLabel(waiting, unsent, overdue)}");
    expect(src).toContain("count={waiting}");
    expect(src).not.toContain("new-client-badge");
    expect(src).not.toMatch(/count=\{unsent\}/);
    expect(read("../app/newclient.css")).not.toContain("new-client-badge");
  });

  it("is refreshed by the header pulse and by adding or cancelling a prospect", () => {
    expect(read("./pendingNewClients.ts")).toContain("pendingCountsStore.set({ unsent: list.unsent, overdue: list.overdue ?? 0, waiting: list.waiting })");
    expect(read("../components/NewClientButton.tsx")).toContain("pendingCountsStore.refresh()");
    expect(read("./pulse.ts")).toMatch(/PULSE_MS = 60_000/);
  });

  it("names every email state and the forms back in words", () => {
    expect(emailStateLabel("sent")).toBe("Sent");
    expect(emailStateLabel("draft")).toContain("draft is in Outlook");
    expect(emailStateLabel("draft_gone")).toContain("no longer in Drafts");
    expect(emailStateLabel("unknown")).toContain("could not be checked");
    expect(formsBackLabel([])).toBe("None yet");
    expect(formsBackLabel(["rif", "laif"])).toBe("Opponent Info Form, Legal Aid Info Form");
  });
});

describe("a press that stopped part-way", () => {
  it("is marked not finished, in words, only while it is", () => {
    expect(isUnfinished({ stage: "folder" })).toBe(true);
    expect(isUnfinished({ stage: "pack" })).toBe(true);
    expect(isUnfinished({ stage: "done" })).toBe(false);
    expect(unfinishedLabel("folder")).toContain("while making the folder");
    expect(unfinishedLabel("pack")).toContain("the folder is made, the forms and the Outlook draft are not");
    expect(unfinishedLabel("done")).toBe("");
    expect(unfinishedLabel(undefined)).toBe("");
  });

  it("says what a finish used and what it made, and nothing for an ordinary press", () => {
    expect(resumedLines({ resumed: false, resumed_notes: [] })).toEqual([]);
    expect(resumedLines({})).toEqual([]);
    expect(resumedLines({ resumed: true, resumed_notes: ["Outlook draft: made now."] })).toEqual([
      "Carried on from the earlier press that stopped part-way. Nothing was made twice.",
      "Outlook draft: made now.",
    ]);
  });

  it("gets a new press id each time, kept for a retry of the same form only", () => {
    const a = newPressId();
    const b = newPressId();
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThan(8);
    expect(a.length).toBeLessThanOrEqual(64);
    const src = read("../components/NewClientButton.tsx");
    expect(src).toContain("pressRef.current.key !== formKey");
    expect(src).toContain("request_id: pressRef.current.id");
  });

  it("offers Finish on the waiting list for an unfinished entry only", () => {
    const src = read("../components/PendingNewClients.tsx");
    expect(src).toMatch(/\{isUnfinished\(item\) && \(\s*<button[^>]*className="cf-btn cf-btn--primary pending-clients-finish"/);
  });
});

const get = (path: string) => new NextRequest(`http://localhost${path}`);
const post = (path: string, body: unknown) => new NextRequest(`http://localhost${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

describe("stub mode: list, cancel, press", () => {
  it("finishes the unfinished one, walks 2, then 1, then 0, and a press adds one", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const list = await (await listRoute.GET(get("/api/new-client/pending"))).json();
    expect(list.unsent).toBe(3);
    expect(list.items.map((i: { full_name: string }) => i.full_name)).toEqual(["Halfa Madetest", "Stubbie Waitingtest", "Testa Pendingname"]);
    expect(list.items.map((i: { stage: string }) => i.stage)).toEqual(["pack", "done", "done"]);
    expect((await (await pulseRoute.GET(get("/api/pulse"))).json()).pending_new_clients).toEqual({ unsent: 3, overdue: 1, waiting: 3 });

    expect((await resumeRoute.POST(post("/api/new-client/pending/resume", { pending_id: 99 }))).status).toBe(422);
    const finished = await (await resumeRoute.POST(post("/api/new-client/pending/resume", { pending_id: 3 }))).json();
    expect(finished.resumed).toBe(true);
    expect(finished.resumed_notes.at(-1)).toBe("Outlook draft: made now.");
    const again = await (await resumeRoute.POST(post("/api/new-client/pending/resume", { pending_id: 3 }))).json();
    expect(again.resumed_notes).toEqual(["Nothing was left to do: the folder, the forms and the Outlook draft were already made."]);
    const two = await (await cancelRoute.POST(post("/api/new-client/pending/cancel", { pending_id: 3 }))).json();
    expect(two.unsent).toBe(2);

    const one = await (await cancelRoute.POST(post("/api/new-client/pending/cancel", { pending_id: 2 }))).json();
    expect(one.unsent).toBe(1);
    const none = await (await cancelRoute.POST(post("/api/new-client/pending/cancel", { pending_id: 1 }))).json();
    expect(none).toEqual({ items: [], unsent: 0, overdue: 0, waiting: 0 });
    expect((await cancelRoute.POST(post("/api/new-client/pending/cancel", { pending_id: 1 }))).status).toBe(422);

    const made = await (
      await newClientRoute.POST(post("/api/new-client", { first_name: "Newa", last_name: "Stubclient", email: "n@example.com", category: "crime" }))
    ).json();
    expect(made.status).toBe("pending");
    expect(Number(made.matter_id)).toBeGreaterThanOrEqual(9100);
    const after = await (await listRoute.GET(get("/api/new-client/pending"))).json();
    expect(after.items.map((i: { pending_id: number }) => i.pending_id)).toEqual([made.pending_id]);
  });

  it("sends only the id and the name to the hub to finish one", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ resumed: true, resumed_notes: [], drafts: [] })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await resumeRoute.POST(post("/api/new-client/pending/resume", { pending_id: "7", evil: "x" }));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client/pending/resume");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ pending_id: 7, by: "tailnet" });
    expect(await res.text()).not.toContain("test-token-not-a-real-secret");
  });

  it("sends only the id and the name to the hub", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.internal:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "test-token-not-a-real-secret");
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], unsent: 0, waiting: 0 })));
    vi.stubGlobal("fetch", fetchMock);
    const res = await cancelRoute.POST(post("/api/new-client/pending/cancel", { pending_id: "7", evil: "x" }));
    expect(res.status).toBe(200);
    expect(String(fetchMock.mock.calls[0][0])).toBe("http://hub.internal:8770/client-viewer/new-client/pending/cancel");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ pending_id: 7, by: "tailnet" });
    await listRoute.GET(get("/api/new-client/pending"));
    expect(String(fetchMock.mock.calls[1][0])).toBe("http://hub.internal:8770/client-viewer/new-client/pending");
  });
});
