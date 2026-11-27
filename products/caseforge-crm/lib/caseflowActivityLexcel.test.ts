import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { courtItems, faceButtonLabel, withoutItem } from "./attention";
import { categoryWords } from "./notificationRules";
import { REGENERATE_QUESTION, autoLine, canGenerate, checklistGaps, closingLetterDate, generateBlockedReason, generateLabel, lexcelRow, madeLine, openingRegenerate } from "./lexcelTypes";
import { canMarkDone, canResetStep, eventStatusWord, isOutstanding, oldestFirst, resetStepQuestion, safeLinks, statusMark } from "./pipelineDisplay";
import { stubLexcel, stubMakeLexcel } from "./stubLexcel";
import { STUB_PORTAL_MATTER, stubMarkDone, stubPipeline, stubResetStep, stubRun } from "./stubPipeline";
import { stubHideReply, stubStatementReplies } from "./stubStatementReplies";
import type { AttentionItem, AttentionResponse } from "./types";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const caseFlow = read("../components/CaseFlowTab.tsx");
const activity = read("../components/ActivityLogTab.tsx");
const lexcelRows = read("../components/LexcelLetters.tsx");
const detail = read("../components/DetailPanel.tsx");
const faces = read("../components/NotificationRow.tsx");
const lexcelClient = read("./lexcel.ts");
const lexcelRoute = read("../app/api/lexcel/route.ts");

describe("Case flow and the Activity log are two tabs", () => {
  it("has a tab each (Case flow on the main page, the log on the extra-details page), and no Lexcel tab", () => {
    const tabs = detail.slice(detail.indexOf("const MAIN_TABS"), detail.indexOf("interface CaseTab"));
    expect(tabs.indexOf('["caseflow", "Case Flow"]')).toBeGreaterThan(0);
    expect(tabs.indexOf('["activity", "Activity log"]')).toBeGreaterThan(tabs.indexOf("const EXTRA_TABS"));
    expect(tabs).not.toContain("lexcel");
    expect(detail).toContain('detailTab === "activity" && matterId && <ActivityLogTab');
    expect(detail).not.toContain("LexcelTab");
  });

  it("keeps the log out of the Case flow tab", () => {
    expect(caseFlow).not.toContain("cf2-log");
    expect(caseFlow).not.toContain("data.events");
    expect(activity).toContain("oldestFirst(rows)");
    expect(activity).not.toContain("newestFirst");
  });

  it("reads the log by itself, so the Activity log checks no step", () => {
    expect(activity).toContain("useActivityLog(matterId)");
    expect(activity).not.toContain("usePipeline");
    const pipeline = read("./pipeline.ts");
    expect(pipeline).toContain("/api/pipeline/events?matter_id=");
    const route = read("../app/api/pipeline/events/route.ts");
    expect(route).toContain('"/client-viewer/pipeline/events"');
    expect(route).not.toContain('"/client-viewer/pipeline",');
  });

  it("marks the open tab's timed re-read, so the hub can answer it from its last picture", () => {
    expect(read("./pipeline.ts")).toContain('${background ? "&poll=1" : ""}');
    expect(read("../app/api/pipeline/route.ts")).toContain('poll ? { poll: "true" } : {}');
  });

  it("runs the log oldest to newest, the direction Case flow runs", () => {
    const rows = oldestFirst([{ created_utc: "2026-10-10T12:00:00Z" }, { created_utc: "2026-10-09T10:00:00Z" }, { created_utc: "2026-10-11T08:00:00Z" }]);
    expect(rows.map((r) => r.created_utc.slice(8, 10))).toEqual(["09", "10", "11"]);
  });

  it("has a word for a step reset in the log", () => {
    expect(eventStatusWord("reset")).toBe("Reset");
  });
});

describe("what was taken out of the Case flow tab", () => {
  it("has no Client's reply block", () => {
    for (const gone of ["Client&apos;s reply", "Client's reply", "Client approved the statement", "Client wants changes", "Clear the reply", "What they want changed", "header smileys", "setStatementReply", "useStatementReplies"]) {
      expect(caseFlow).not.toContain(gone);
    }
  });

  it("has no reset of every step", () => {
    expect(caseFlow).not.toContain("Reset the marks for a fresh run");
    expect(caseFlow).not.toContain("resetPipeline(");
    expect(read("./pipeline.ts")).not.toContain("export async function resetPipeline(");
  });
});

describe("the reset beside each step", () => {
  it("is offered on a step that has a mark, and keeps the old promise", () => {
    expect(canResetStep({ status: "done", resettable: true })).toBe(true);
    expect(canResetStep({ status: "done", resettable: false })).toBe(false);
    expect(canResetStep({ status: "todo", resettable: false })).toBe(false);
    expect(canResetStep({ status: "done" })).toBe(true);
    const question = resetStepQuestion({ number: 8, label: "Court pack ready" });
    expect(question).toContain("step 8");
    expect(question).toContain("Only this step");
    expect(question).toContain("Files, folders, drafts and envelopes are NOT deleted");

    expect(caseFlow).toContain('{...opens(step, "reset", openForm)}');
    expect(read("./pipeline.ts")).toContain("return resetPipelineStep(matterId, step);");
    expect(read("./pipelineForms.ts")).toContain("explain: resetStepQuestion(step)");
    expect(caseFlow).toContain("deletes no files, folders, drafts or envelopes");
  });

  it("forgets only that step in the stub", () => {
    const id = "stub-reset-test";
    stubMarkDone(id, "folder", "Sam", "");
    stubMarkDone(id, "statement", "Sam", "");
    const out = stubResetStep(id, "folder", "Sam");
    if ("error" in out) throw new Error(out.error);
    const status = (key: string) => out.steps.find((s) => s.key === key)?.status;
    expect(status("folder")).not.toBe("done");
    expect(status("statement")).toBe("done");
    expect(status("record")).toBe("done");
    expect(out.events.at(-1)).toMatchObject({ step: "folder", status: "reset", by: "Sam" });
    expect(out.steps.find((s) => s.key === "statement")?.resettable).toBe(true);
  });
});

describe("a step that is not needed", () => {
  it("is its own state: not to do, not outstanding, nothing to mark or press", () => {
    expect(statusMark("not_needed").word).toBe("Not needed");
    expect(statusMark("not_needed").word).not.toBe(statusMark("todo").word);
    expect(isOutstanding({ status: "not_needed" })).toBe(false);
    expect(isOutstanding({ status: "done" })).toBe(false);
    expect(isOutstanding({ status: "todo" })).toBe(true);
    expect(canMarkDone({ status: "not_needed" })).toBe(false);
    expect(caseFlow).toContain('step.status === "not_needed" ? []');
  });

  it("is how the stub shows step 15 with nobody added, and it never holds up step 16", () => {
    const id = "stub-not-needed-test";
    for (const key of ["folder", "statement", "court_pack", "court_email", "court_reply", "serve"]) stubMarkDone(id, key, "Sam", "");
    stubRun(id, "email", "Sam", "loa_signing");
    const steps = stubPipeline(id).steps;
    const fifteen = steps.find((s) => s.key === "serve_other");
    expect(fifteen).toMatchObject({ status: "not_needed", actor: "", can_run: false });
    expect(steps.find((s) => s.key === "sos_received")?.status).toBe("todo");
    expect(steps.filter(isOutstanding).map((s) => s.key)).not.toContain("serve_other");
  });
});

describe("a portal-only court", () => {
  it("drafts no court email in the stub and waits for a person to mark it filed", () => {
    for (const key of ["folder", "statement", "court_pack"]) stubMarkDone(STUB_PORTAL_MATTER, key, "Sam", "");
    stubRun(STUB_PORTAL_MATTER, "email", "Sam", "loa_signing");
    const nine = stubPipeline(STUB_PORTAL_MATTER).steps.find((s) => s.key === "court_email");
    expect(nine?.status).toBe("attention");
    expect(nine?.summary).toContain("only through the online portal");
    expect(nine?.variants).toEqual([{ key: "portal_filed", label: "I have filed it through the portal" }]);
    const out = stubRun(STUB_PORTAL_MATTER, "court_email", "Sam", "portal_filed");
    if ("error" in out) throw new Error(out.error);
    expect(out.message).toContain("No court email was drafted");
    expect(out.pipeline.steps.find((s) => s.key === "court_email")?.status).toBe("done");
  });
});

describe("links", () => {
  it("shows only https links", () => {
    expect(safeLinks([{ label: "a", url: "https://example.invalid/a" }, { label: "b", url: "javascript:alert(1)" }, { label: "c", url: "" }])).toEqual([{ label: "a", url: "https://example.invalid/a" }]);
    expect(safeLinks(undefined)).toEqual([]);
  });

  it("opens them in a new tab from the steps, the log and the Lexcel letters", () => {
    for (const src of [caseFlow, activity, lexcelRows]) {
      expect(src).toContain("safeLinks(");
      expect(src).toContain('target="_blank" rel="noreferrer"');
    }
  });
});

describe("the closing letter's date on the Client tab", () => {
  const closing = (made: boolean, made_utc: string) => ({
    letters: [{ ...stubLexcel("stub-lexcel-new").letters.find((l) => l.kind === "closing")!, made, made_utc }],
  });

  it("is the date the closing letter step made it, from the Lexcel record, and nothing when not made", () => {
    expect(closingLetterDate(closing(true, "2026-10-12T23:30:00Z"))).toBe("13 October 2026");
    expect(closingLetterDate(closing(false, ""))).toBe("");
    expect(closingLetterDate(closing(true, "not a date"))).toBe("Made, date not recorded");
    expect(closingLetterDate(null)).toBe("");
  });

  it("is not in the Client tab (it is on the Details tab's Lexcel rows), read without the letters' checklists", () => {
    const client = detail.slice(detail.indexOf('{detailTab === "client" && ('), detail.indexOf('{detailTab === "details"'));
    expect(client).not.toContain("<ClosingLetterField");
    expect(lexcelClient).toContain("fetchLexcel(matterId, { advice: false })");
    expect(lexcelRoute).toContain('params.advice = "false"');
  });
});

describe("the Lexcel section of the Details tab", () => {
  const row = (matter: string, kind: string) => lexcelRow(stubLexcel(matter).letters.find((l) => l.kind === kind), false);

  it("sits under Details, below Legal aid, with the three letters as rows", () => {
    const details = detail.slice(detail.indexOf('{detailTab === "details" && ('), detail.indexOf('{detailTab === "caseflow"'));
    expect(details.indexOf('<h3 className="detail-section-title">Lexcel</h3>')).toBeGreaterThan(details.indexOf('<h3 className="detail-section-title">Legal aid</h3>'));
    expect(details).toContain("<LexcelLetters key={`lexcel-${matterId}`} matterId={matterId}");
    expect(stubLexcel("stub-lexcel-new").letters.map((l) => l.kind)).toEqual(["opening", "mid", "closing"]);
    expect(lexcelRows).toContain('{ kind: "opening", label: "Opening client care letter" }');
    expect(lexcelRows).toContain('{ kind: "mid", label: "Court outcome letter" }');
    expect(lexcelRows).toContain('{ kind: "closing", label: "Closing letter" }');
  });

  it("looks like the Letter of authority marker: a box, nothing written for a letter not made, and Generate under it", () => {
    expect(lexcelRows).toContain('className="detail-field matter-marker lexcel-row" data-state={view.state}');
    expect(lexcelRows).toContain('className="matter-marker-box"');
    expect(lexcelRows).toContain('? "Generating…" : autoLine(letter) ? "Make now" : generateLabel(letter)}');
    expect(row("9001", "closing")).toMatchObject({ state: "missing", text: "", url: "", canGenerate: true });
    expect(lexcelRow(undefined, false)).toMatchObject({ state: "loading", text: "Checking…", canGenerate: false });
    expect(lexcelRow(undefined, true)).toMatchObject({ state: "unknown", text: "Couldn't check", canGenerate: false });
  });

  it("ticks a made letter with the date it was made, a link to it, and Generate greyed out: none, some, all", () => {
    expect(["opening", "mid", "closing"].map((k) => row("9001", k).state)).toEqual(["missing", "missing", "missing"]);
    expect(["opening", "mid", "closing"].map((k) => row("9002", k).state)).toEqual(["received", "missing", "missing"]);
    expect(["opening", "mid", "closing"].map((k) => row("9003", k).state)).toEqual(["received", "received", "received"]);
    const made = row("9002", "opening");
    expect(made).toMatchObject({ text: "2 Oct 2026", url: "https://example.invalid/stub/lexcel/9002/opening", canGenerate: true });
    expect(made.title).toBe("Made on 2 October 2026 by auto, by Case flow.");
    expect(generateBlockedReason({ canGenerate: true, running: false, made: true })).toBe("");
    expect(generateBlockedReason({ canGenerate: true, running: true, made: false })).toBe("A letter is being made.");
    expect(generateBlockedReason({ canGenerate: true, running: false, made: false })).toBe("");
    expect(lexcelRows).toContain('disabled={!letter || reason !== ""');
    expect(madeLine(stubLexcel("9001").letters[0])).toBe("Not recorded as made.");
    expect(madeLine({ made: true, made_utc: "2026-10-12T09:00:00Z", made_by: "Sam", made_via: "Lexcel", times: 2 })).toBe(
      "Made on 12 October 2026 by Sam, with a Lexcel button (2 made; this is the newest).",
    );
    expect(lexcelRow({ ...stubLexcel("9003").letters[1], times: 2 }, false).text).toBe("5 Oct 2026 (2 made)");
    expect(stubLexcel("9003").letters.every((l) => l.links[0]?.url.startsWith("https://"))).toBe(true);
  });

  it("takes the date from the Lexcel record and never a link that is not https", () => {
    const letter = { ...stubLexcel("9003").letters[2], made_utc: "2026-10-12T23:30:00Z", links: [{ label: "x", url: "javascript:alert(1)" }] };
    expect(lexcelRow(letter, false)).toMatchObject({ state: "received", text: "13 Oct 2026", url: "" });
    expect(lexcelRow({ ...letter, made_utc: "" }, false).text).toBe("Made");
  });

  it("Generate is always there, and says Regenerate once a letter was made or is in the folder", () => {
    expect(canGenerate({ made: true })).toBe(true);
    expect(generateLabel({ made: false })).toBe("Generate");
    expect(generateLabel({ made: true })).toBe("Regenerate");
    expect(generateLabel({ made: false, file_present: true })).toBe("Regenerate");
    expect(generateLabel(undefined)).toBe("Generate");
  });

  describe("the opening letter's Regenerate", () => {
    const opening = (matter: string) => stubLexcel(matter).letters.find((l) => l.kind === "opening")!;
    const idle = { confirming: false, running: false, outcome: null };

    it("is available once the letter is made, and only for the opening letter's Regenerate", () => {
      expect(openingRegenerate(opening("9002"), idle)).toEqual({
        state: "available",
        disabled: false,
        title: "Make a new letter beside the old one, as a draft. Nothing is sent and nothing is deleted.",
      });
      expect(openingRegenerate({ ...opening("9001"), file_present: true }, idle)?.state).toBe("available");
      expect(openingRegenerate(opening("9001"), idle)).toBeNull();
      expect(openingRegenerate(stubLexcel("9003").letters.find((l) => l.kind === "closing"), idle)).toBeNull();
      expect(openingRegenerate(undefined, idle)).toBeNull();
      expect(lexcelRows).not.toContain("not built yet");
    });

    it("asks first, on the row, in plain words, and is greyed out while asking or making", () => {
      expect(openingRegenerate(opening("9002"), { ...idle, confirming: true })).toMatchObject({ state: "confirming", disabled: true });
      expect(openingRegenerate(opening("9002"), { ...idle, running: true })).toMatchObject({ state: "running", disabled: true });
      expect(REGENERATE_QUESTION).toContain("new draft beside the old one");
      expect(REGENERATE_QUESTION).toContain("Nothing is sent and nothing is deleted.");
      expect(lexcelRows).toContain("if (regen) return setConfirming(fixed.kind);");
      expect(lexcelRows).toContain('void make(letter, "regenerate", true);');
      expect(lexcelRows).toContain("Yes, make a new letter");
    });

    it("makes a new letter beside the old one and says it is done", () => {
      const id = "9002";
      const out = stubMakeLexcel(id, "opening", "Sam", "regenerate");
      if ("error" in out) throw new Error(out.error);
      expect(out.ok).toBe(true);
      expect(out.message).toContain("beside the earlier one");
      expect(out.message).toContain("Nothing was sent.");
      const again = out.lexcel.letters.find((l) => l.kind === "opening")!;
      expect(again).toMatchObject({ made: true, made_by: "Sam", times: 2 });
      expect(openingRegenerate(again, { ...idle, outcome: { ok: true } })).toMatchObject({ state: "done", disabled: false });
    });

    it("is refused once the letter is signed or sent, with the reason shown", () => {
      const signed = opening("9003");
      expect(signed.locked).toContain("signed");
      expect(openingRegenerate(signed, idle)).toEqual({ state: "refused", disabled: true, title: signed.locked });
      expect(openingRegenerate(signed, { ...idle, confirming: true })?.state).toBe("refused");
      const pressed = stubMakeLexcel("9003", "opening", "Sam", "regenerate");
      if ("error" in pressed) throw new Error(pressed.error);
      expect(pressed).toMatchObject({ ok: false });
      expect(pressed.message).toBe(`Not made: ${signed.locked}`);
      expect(lexcelRows).toContain('{regen?.state === "refused" && <p className="lexcel-note lexcel-locked">Regenerate is not available: {regen.title}</p>}');
    });
  });

  it("lists what a letter would be missing without stopping it", () => {
    const letter = { checklist: [{ key: "address", label: "Client's address", ok: false, note: "Not on record." }, { key: "email", label: "Client's email", ok: true, note: "" }] };
    expect(checklistGaps(letter).map((c) => c.key)).toEqual(["address"]);
    expect(checklistGaps(undefined)).toEqual([]);
  });

  it("records a letter when Generate makes it, and never makes a second closing letter", () => {
    const id = "stub-lexcel-make";
    const out = stubMakeLexcel(id, "closing", "Sam");
    if ("error" in out) throw new Error(out.error);
    expect(out.ok).toBe(true);
    expect(out.lexcel.letters.find((l) => l.kind === "closing")).toMatchObject({ made: true, made_by: "Sam", made_via: "Lexcel", can_make: false });
    expect(out.lexcel.letters.find((l) => l.kind === "opening")?.made).toBe(false);
    const again = stubMakeLexcel(id, "closing", "Sam");
    if ("error" in again) throw new Error(again.error);
    expect(again.ok).toBe(false);
    expect(stubMakeLexcel(id, "audit", "Sam")).toEqual({ error: "say which letter: opening, mid or closing" });
    expect(stubMakeLexcel(id, "opening", " ")).toEqual({ error: "type your name first" });
    expect(lexcelRows).toContain("makeLexcelLetter(matterId, letter.kind, variant)");
    expect(lexcelRows).toContain("nothing is sent");
  });

  it("shows a refusal in the maker's own words, with the override the refusal offers", () => {
    const id = "9001";
    const refused = stubMakeLexcel(id, "opening", "Sam");
    if ("error" in refused) throw new Error(refused.error);
    expect(refused).toMatchObject({ ok: false, offers: [{ key: "force", label: "Make it anyway: skip the 7-day referral check" }] });
    expect(refused.message).toContain("7-day");
    expect(refused.lexcel.letters[0].made).toBe(false);
    expect(stubMakeLexcel(id, "closing", "Sam", "force")).toEqual({ error: "that is not a choice this letter offers" });
    expect(lexcelRows).toContain('{outcome.ok ? "Done: " : /^not made\\b/i.test(outcome.message) ? "" : "Not made: "}');
    expect(lexcelRows).toContain("(outcome?.offers ?? []).map((offer) => (");
    expect(lexcelRows).toContain('role={outcome.ok ? "status" : "alert"}');
  });

  it("keeps the mid-case letter's Generate until every hearing has its letter and that letter's email", () => {
    const id = "9002";
    expect(row(id, "mid")).toMatchObject({ state: "missing", canGenerate: true, note: "Generate makes the letter for the hearing on 1 October 2026." });
    const letter = stubMakeLexcel(id, "mid", "Sam");
    if ("error" in letter) throw new Error(letter.error);
    expect(letter.ok).toBe(true);
    expect(row(id, "mid")).toMatchObject({ state: "received", canGenerate: true, note: "Generate drafts the email for the letter about the hearing on 1 October 2026." });
    const email = stubMakeLexcel(id, "mid", "Sam");
    if ("error" in email) throw new Error(email.error);
    expect(email.links[0].label).toBe("Open the draft in Outlook");
    expect(row(id, "mid")).toMatchObject({ state: "received", canGenerate: true, note: "Every hearing that has happened has its letter." });
    const none = stubMakeLexcel("stub-lexcel-no-hearing", "mid", "Sam");
    if ("error" in none) throw new Error(none.error);
    expect(none).toMatchObject({ ok: false, message: "No hearing is waiting for an outcome letter." });
  });

  it("reads once from stored state: no polling and no Case flow picture", () => {
    const hook = read("./lexcel.ts");
    expect(hook).toContain("/api/lexcel?matter_id=");
    expect(hook).not.toContain("startVisiblePoll");
    expect(lexcelRows).not.toContain("usePipeline");
    expect(read("../app/api/lexcel/route.ts")).toContain('hubGetJson(request, "/client-viewer/lexcel"');
  });

  it("says it does not search the folders", () => {
    expect(lexcelRows).toContain("folders are not searched");
  });
});

describe("the intro link under the client's name", () => {
  it("links Referral Info to the stored intro or new client form and stays plain text without one", () => {
    expect(detail).toContain('<ClientRoleLine matterId={matterId} role={match.client_role ?? ""} />');
    expect(detail).toContain("Referral Info");
    expect(detail).toContain('<a className="detail-subtitle-link" href={introUrl} target="_blank" rel="noopener noreferrer" title="Open the referral info">');
  });

  it("costs one light read of stored state, not the markers' folder search", () => {
    expect(detail).toContain("backgroundFetch(`/api/clients/intro-link?matter_id=");
    const route = read("../app/api/clients/intro-link/route.ts");
    expect(route).toContain('"/client-viewer/intro-link"');
    expect(route).not.toContain("/client-viewer/matter-markers");
    expect(read("../components/MatterMarkers.tsx")).toContain("new CustomEvent(INTRO_FOUND_EVENT, { detail: { matterId, url: intro.url } })");
  });
});

describe("the witness statement replies on the one bell", () => {
  it("gives each witness statement entry a Done button", () => {
    expect(faces).toContain('{busy ? "Saving..." : "Done"}');
    expect(faces).toContain("hideStatementReply(n.matter_id)");
    const before = stubStatementReplies();
    const approved = before.items.filter((i) => i.state === "approved");
    expect(approved.length).toBeGreaterThan(0);
    expect(stubHideReply(approved[0].matter_id, "Sam")).toEqual({ matter_id: approved[0].matter_id, state: "approved" });
    const after = stubStatementReplies();
    expect(after.approved_count).toBe(before.approved_count - 1);
    expect(after.items.map((i) => i.matter_id)).not.toContain(approved[0].matter_id);
    expect(stubHideReply("12345", "Sam")).toEqual({ error: "there is no statement reply for this matter" });
    expect(stubHideReply(after.items[0].matter_id, " ")).toEqual({ error: "type your name first" });
  });

  it("puts a court's order on the smiley and every court rejection on the frowny", () => {
    const item = (over: Partial<AttentionItem>): AttentionItem => ({
      task_id: "a:1", matter_id: "9001", who: "Stub Testperson", kind: "court_order", label: "", complaint_domain: "", settlement_stage: "",
      subject: "", summary: "", deadline: "", importance: "normal", created: "", web_link: "", ...over,
    });
    const data: AttentionResponse = {
      configured: true, red_count: 0, yellow_count: 0, green_count: 0, red: [], yellow: [], green: [],
      court_order: [item({ task_id: "a:1" })], court_order_count: 1,
      court_rejected: [item({ task_id: "a:2", kind: "court_rejected" }), item({ task_id: "a:3", kind: "court_rejected" })], court_rejected_count: 2,
    };
    expect(courtItems(data, "order").count).toBe(1);
    expect(courtItems(data, "rejected").items.map((i) => i.task_id)).toEqual(["a:2", "a:3"]);
    expect(courtItems(null, "order")).toEqual({ items: [], count: 0 });
    expect(faceButtonLabel("smile", 0, 0, 1)).toBe("Approved and accepted, 1 court order");
    expect(faceButtonLabel("frown", 1, 0, 2)).toBe("Wants changes or declined, 1 statement needing changes, 2 court rejections");
    const out = withoutItem(data, "a:2");
    expect(out.court_rejected_count).toBe(1);
    expect(out.court_order_count).toBe(1);
    expect(categoryWords("court_rejected")).toBe("✕ Court rejected");
    expect(categoryWords("court_order")).toBe("✓ Court order received");
  });
});

describe("autoLine: the opening letter's countdown for a client on Auto", () => {
  const counting = { made: false, auto: { state: "counting" as const, days_left: 3, due_on: "2026-10-20" } };
  it("counts down in working days and says what is made", () => {
    expect(autoLine(counting)).toBe("Generating in 3 days: the letter, its Documenso envelope and the email draft. Nothing is sent.");
    expect(autoLine({ made: false, auto: { state: "counting", days_left: 1 } })).toMatch(/^Generating in 1 day:/);
    expect(autoLine({ made: false, auto: { state: "due" } })).toMatch(/^Generating now/);
  });
  it("says when the hold or a cancel stops it", () => {
    expect(autoLine({ made: false, auto: { ...counting.auto, held: true } })).toMatch(/paused: automatic drafting is on hold/);
    expect(autoLine({ made: false, auto: { ...counting.auto, cancelled: true, cancelled_by: "Sam" } })).toBe(
      "Automatic letter cancelled by Sam. Make now still makes it.",
    );
  });
  it("is empty once made, or for a client not on Auto", () => {
    expect(autoLine({ ...counting, made: true })).toBe("");
    expect(autoLine({ made: false })).toBe("");
  });
});
