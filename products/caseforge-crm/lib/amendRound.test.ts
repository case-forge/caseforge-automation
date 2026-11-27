import { describe, expect, it } from "vitest";
import {
  AMEND_ANSWERS_MAX,
  AMEND_EDIT_MAX,
  AMEND_EMAIL_MAX,
  AMEND_FLAG_LABELS,
  AMEND_HUB_PATHS,
  amendFlagLabel,
  amendRoundSummary,
  approveLabel,
  checkAmendRequest,
  decideBlockedReason,
  editProblem,
  flaggedLine,
  hubBodyFor,
  paragraphHeading,
  paragraphsToCheck,
  prepareBlockedReason,
  repeatLine,
  wordDiff,
} from "./amendRound";
import { canMarkDone, canResetStep } from "./pipelineDisplay";
import { HUB_MAP } from "./gameFlow";
import { stubAmendApprove, stubAmendDiscard, stubAmendPrepare, stubMarkDone, stubPipeline, stubResetStep, stubRun } from "./stubPipeline";
import { PIPELINE_STEP_NUMBERS } from "./pipelineTypes";
import type { AmendParagraph } from "./pipelineTypes";

const para = (over: Partial<AmendParagraph>): AmendParagraph => ({ id: "p1", para: 1, before: "a", after: "b", why: "", client_words: "", flags: [], ...over });

describe("checkAmendRequest", () => {
  it("refuses an unknown action, a missing matter or a missing name", () => {
    expect(checkAmendRequest({ action: "send", matter_id: "1", by: "Sam" })).toEqual({ error: expect.stringMatching(/prepare, approve or discard/) });
    expect(checkAmendRequest({ action: "prepare", by: "Sam", email_text: "x" })).toEqual({ error: "matter_id is required" });
    expect(checkAmendRequest({ action: "prepare", matter_id: "1", by: "  ", email_text: "x" })).toEqual({ error: "type your name first" });
  });

  it("needs the email to prepare, trimmed and cut to 60000 characters", () => {
    expect(checkAmendRequest({ action: "prepare", matter_id: "1", by: "Sam", email_text: "   " })).toHaveProperty("error");
    const out = checkAmendRequest({ action: "prepare", matter_id: " 1 ", by: "Sam", email_text: `  ${"x".repeat(AMEND_EMAIL_MAX + 50)}  ` });
    expect("body" in out && out.body.action === "prepare" && out.body.email_text.length).toBe(AMEND_EMAIL_MAX);
    expect("body" in out && out.body.matter_id).toBe("1");
  });

  it("needs a positive whole round to approve or discard", () => {
    for (const round of [0, -1, 1.5, "x", null, undefined]) {
      expect(checkAmendRequest({ action: "discard", matter_id: "1", by: "Sam", round })).toEqual({ error: "round must be a positive whole number" });
    }
    expect(checkAmendRequest({ action: "discard", matter_id: "1", by: "Sam", round: "2" })).toEqual({ body: { action: "discard", matter_id: "1", by: "Sam", round: 2 } });
  });

  it("passes the owner's edited questions for the client through, trimmed, empty ones dropped, and refuses a bad list", () => {
    const out = checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, client_questions: [" Which date is right? ", "  "] });
    expect(out).toEqual({ body: { action: "approve", matter_id: "1", by: "Sam", round: 1, answers: "", keep_original: [], client_questions: ["Which date is right?"] } });
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, client_questions: "x" })).toHaveProperty("error");
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, client_questions: Array(9).fill("q") })).toHaveProperty("error");
  });

  it("cuts the answers to 5000 and keeps only short paragraph ids, once each", () => {
    const out = checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, answers: "y".repeat(AMEND_ANSWERS_MAX + 9), keep_original: ["p4", " p4 ", "new1"] });
    expect(out).toHaveProperty("body");
    if ("body" in out && out.body.action === "approve") {
      expect(out.body.answers.length).toBe(AMEND_ANSWERS_MAX);
      expect(out.body.keep_original).toEqual(["p4", "new1"]);
    }
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, keep_original: "p4" })).toHaveProperty("error");
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, keep_original: [4] })).toHaveProperty("error");
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1, keep_original: ["x".repeat(41)] })).toHaveProperty("error");
    expect(checkAmendRequest({ action: "approve", matter_id: "1", by: "Sam", round: 1 })).toEqual({
      body: { action: "approve", matter_id: "1", by: "Sam", round: 1, answers: "", keep_original: [] },
    });
  });

  it("takes the owner's own text per paragraph: one line, trimmed, never empty, long or numbered", () => {
    const base = { action: "approve", matter_id: "1", by: "Sam", round: 1 };
    const out = checkAmendRequest({ ...base, edits: { p4: "  My words.\nOn two lines.  " } });
    expect(out).toHaveProperty("body");
    if ("body" in out && out.body.action === "approve") expect(out.body.edits).toEqual({ p4: "My words. On two lines." });
    expect(checkAmendRequest({ ...base, edits: { p4: "   " } })).toHaveProperty("error");
    expect(checkAmendRequest({ ...base, edits: { p4: "x".repeat(AMEND_EDIT_MAX + 1) } })).toHaveProperty("error");
    expect(checkAmendRequest({ ...base, edits: { p4: "5. Mine." } })).toHaveProperty("error");
    expect(checkAmendRequest({ ...base, edits: { p4: 3 } })).toHaveProperty("error");
    expect(checkAmendRequest({ ...base, edits: ["a"] })).toHaveProperty("error");
    expect(checkAmendRequest({ ...base, edits: { ["x".repeat(41)]: "Mine." } })).toHaveProperty("error");
  });

  it("explains an edit that cannot be used", () => {
    expect(editProblem("Fine text.")).toBe("");
    expect(editProblem("  ")).toMatch(/empty/);
    expect(editProblem("12) Numbered")).toMatch(/number/);
    expect(editProblem("x".repeat(AMEND_EDIT_MAX + 1))).toMatch(/too long/);
  });

  it("sends the hub the body without the action, to the action's own path", () => {
    expect(hubBodyFor({ action: "discard", matter_id: "1", by: "Sam", round: 2 })).toEqual({ matter_id: "1", by: "Sam", round: 2 });
    expect(AMEND_HUB_PATHS.approve).toBe("/client-viewer/pipeline/amend/approve");
  });
});

describe("words for a round", () => {
  it("labels every flag in plain words, with a fallback", () => {
    expect(AMEND_FLAG_LABELS.review.badge).toBe("REVIEW");
    expect(AMEND_FLAG_LABELS.review.meaning).toMatch(/missing from the new text/);
    expect(amendFlagLabel("editorial").badge).toBe("Editorialising");
    expect(amendFlagLabel("changed_often").badge).toBe("Changed in 3+ rounds");
    expect(amendFlagLabel("merged").badge).toBe("Text from another paragraph");
    expect(amendFlagLabel("facts_unread").badge).toBe("Facts not read");
    expect(amendFlagLabel("asked_again").badge).toBe("Asked again");
    expect(amendFlagLabel("mystery").badge).toBe("Check");
  });

  it("sums a round up and names the paragraphs to check", () => {
    const paragraphs = [para({ id: "p1" }), para({ id: "p2", flags: [{ kind: "review", text: "" }] }), para({ id: "p3", flags: [{ kind: "merged", text: "" }] }), para({ id: "new1", para: null })];
    const round = { paragraphs, questions: [{ para: null, type: "asks_advice" as const, client_words: "?" }] };
    expect(amendRoundSummary(round)).toBe("3 paragraphs changed, 1 new paragraph, 2 to check, 1 question to answer");
    expect(paragraphsToCheck(round).map((p) => p.id)).toEqual(["p2", "p3"]);
    expect(amendRoundSummary({ paragraphs: [para({})], questions: [] })).toBe("1 paragraph changed");
    expect(paragraphHeading({ para: 4 })).toBe("Paragraph 4");
    expect(paragraphHeading({ para: null })).toMatch(/^New paragraph/);
  });

  it("says when the client is flagged, and what a repeat is", () => {
    expect(flaggedLine({ rounds: 2, flagged: false, open: null })).toBe("");
    expect(flaggedLine({ rounds: 3, flagged: true, open: null })).toBe("Round 3: this client is flagged (3 or more rounds).");
    expect(repeatLine({ earlier_round: 1, in_text_now: false })).toBe("Asked again: first asked in round 1; NOT in the text now.");
    expect(repeatLine({ earlier_round: 2, in_text_now: true })).toMatch(/already in the text now/);
    expect(approveLabel("prepared")).toBe("Approve: save the statement and draft the email");
    expect(approveLabel("saved")).toBe("Draft email (the statement is already saved)");
  });

  it("says why a button cannot be pressed, the lock first", () => {
    const ok = { canStart: true, startBlocked: "", locked: "", busy: false, hasEmail: true };
    expect(prepareBlockedReason(ok)).toBe("");
    expect(prepareBlockedReason({ ...ok, locked: "Locked" })).toBe("Locked");
    expect(prepareBlockedReason({ ...ok, canStart: false, startBlocked: "No statement yet." })).toBe("No statement yet.");
    expect(prepareBlockedReason({ ...ok, hasEmail: false })).toMatch(/email/);
    expect(decideBlockedReason({ locked: "", busy: true })).toMatch(/running/);
  });
});

describe("wordDiff", () => {
  const join = (parts: ReturnType<typeof wordDiff>, keep: "del" | "ins") => parts.filter((p) => p.kind === "same" || p.kind === keep).map((p) => p.text).join("");

  it("marks only the words that changed and gives both texts back", () => {
    const before = "He came at 9pm and shouted.";
    const after = "He came at 10pm and shouted loudly.";
    const parts = wordDiff(before, after);
    expect(join(parts, "del")).toBe(before);
    expect(join(parts, "ins")).toBe(after);

    expect(parts.filter((p) => p.kind === "del").map((p) => p.text.trim())).toEqual(["9pm"]);
    expect(parts.filter((p) => p.kind === "ins").map((p) => p.text.trim())).toEqual(["10pm", "loudly"]);
  });

  it("keeps a full stop out of the change when words are added before it", () => {
    const parts = wordDiff("shouted through the door.", "shouted through the door for twenty minutes.");
    expect(parts.filter((p) => p.kind === "del")).toEqual([]);
    expect(parts.filter((p) => p.kind === "ins").map((p) => p.text.trim())).toEqual(["for twenty minutes"]);
  });

  it("handles an empty side and a change only in spacing", () => {
    expect(wordDiff("", "New text.")).toEqual([{ kind: "ins", text: "New text." }]);
    const parts = wordDiff("a  b", "a b");
    expect(join(parts, "del")).toBe("a  b");
    expect(join(parts, "ins")).toBe("a b");
  });
});

describe("step 6 can be marked done by hand, and reset only then", () => {
  it("offers Mark done while outstanding, and Reset only for a mark of its own", () => {
    expect(canMarkDone({ key: "amend", status: "attention" })).toBe(true);
    expect(canMarkDone({ key: "amend", status: "blocked" })).toBe(true);
    expect(canMarkDone({ key: "amend", status: "todo" })).toBe(true);
    expect(canMarkDone({ key: "amend", status: "done" })).toBe(false);
    expect(canMarkDone({ key: "amend", status: "not_needed" })).toBe(false);
    expect(canResetStep({ key: "amend", status: "done", resettable: true })).toBe(true);
    expect(canResetStep({ key: "amend", status: "done", resettable: false })).toBe(false);
    expect(canResetStep({ key: "amend", status: "done" })).toBe(false);
    expect(canMarkDone({ key: "email", status: "attention" })).toBe(true);
  });

  it("is not needed in the demo game", () => {
    expect(HUB_MAP.amend.notNeeded).toMatch(/^Not needed/);
  });
});

describe("stub amendment round", () => {
  it("shows step 6 not needed with a round ready to start, and never holds up step 8", () => {
    const p = stubPipeline("amend-t1");
    const step = p.steps.find((s) => s.key === "amend");
    expect(step?.number).toBe(PIPELINE_STEP_NUMBERS.amend);
    expect(step?.status).toBe("not_needed");
    expect(step?.can_run).toBe(false);
    expect(step?.amend).toMatchObject({ rounds: 0, flagged: false, can_start: true, start_blocked: "", open: null });

    expect(stubPipeline("amend-t1").steps.find((s) => s.key === "email")?.status).toBe("blocked");
    for (const k of ["folders", "unpack", "statement"]) stubRun("amend-t1", k, "C", "");
    expect(stubPipeline("amend-t1").steps.find((s) => s.key === "email")?.can_run).toBe(true);
    expect(stubPipeline("amend-t1").steps.find((s) => s.key === "court_pack")?.status).toBe("blocked");
    stubRun("amend-t1", "email", "C", "loa_signing");
    expect(stubPipeline("amend-t1").steps.find((s) => s.key === "court_pack")?.can_run).toBe(true);
    expect(stubPipeline("amend-t1").steps.find((s) => s.key === "ws_sign")?.status).toBe("not_needed");
    expect(stubRun("amend-t1", "amend", "C", "")).toHaveProperty("error");
    expect(stubResetStep("amend-t1", "amend", "C")).toHaveProperty("error");
    const marked = stubMarkDone("amend-t1", "amend", "C", "By phone.");
    expect("error" in marked).toBe(false);
    const markedStep = !("error" in marked) ? marked.steps.find((s) => s.key === "amend") : undefined;
    expect(markedStep).toMatchObject({ status: "done", outside: "by_hand", resettable: true });
    expect(stubMarkDone("amend-t1", "amend", "C", "")).toHaveProperty("error");
    const reset = stubResetStep("amend-t1", "amend", "C");
    expect(!("error" in reset) && reset.steps.find((s) => s.key === "amend")?.status).toBe("not_needed");
  });

  it("refuses Mark done while a round is waiting", () => {
    stubAmendPrepare("amend-t3", "Sam", "Please change paragraph 4.");
    expect(stubMarkDone("amend-t3", "amend", "Sam", "")).toHaveProperty("error");
  });

  it("prepares, approves and discards a round", () => {
    const prepared = stubAmendPrepare("amend-t2", "Sam", "Please change paragraph 4.");
    expect("error" in prepared).toBe(false);
    const step = !("error" in prepared) ? prepared.steps.find((s) => s.key === "amend") : undefined;
    expect(step?.status).toBe("attention");
    expect(step?.actor).toBe("you");
    expect(step?.amend?.open?.round).toBe(1);
    expect(step?.amend?.can_start).toBe(false);
    expect(stubAmendPrepare("amend-t2", "Sam", "again")).toHaveProperty("error");
    expect(stubAmendApprove("amend-t2", "Sam", 2, "", [])).toHaveProperty("error");

    const approved = stubAmendApprove("amend-t2", "Sam", 1, "The hearing date comes from the court.", ["p7"]);
    expect(approved).toMatchObject({ ok: true });
    if (!("error" in approved)) {
      expect(approved.message).toMatch(/Nothing was sent/);
      expect(approved.pipeline.steps.find((s) => s.key === "amend")?.amend).toMatchObject({ rounds: 1, open: null, can_start: true });
    }

    stubAmendPrepare("amend-t2", "Sam", "More changes.");
    const second = stubPipeline("amend-t2").steps.find((s) => s.key === "amend")?.amend?.open;
    expect(second?.round).toBe(2);
    expect(second?.repeats.length).toBeGreaterThan(0);
    const discarded = stubAmendDiscard("amend-t2", "Sam", 2);
    expect("error" in discarded ? null : discarded.steps.find((s) => s.key === "amend")?.status).toBe("not_needed");
    expect(stubAmendDiscard("amend-t2", "Sam", 2)).toHaveProperty("error");
  });
});
