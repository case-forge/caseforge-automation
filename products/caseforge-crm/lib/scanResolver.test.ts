import { describe, expect, it } from "vitest";
import { ambiguityNote, bestGuess, confidenceLabel, confirmBlockedReason, confirmCopiesWarning, kindLabel } from "./scanResolver";
import { stubCandidates, stubClientScans, stubConfirm } from "./stubScans";

describe("confidence is worded, never only a number", () => {
  it("says the number and the word", () => {
    expect(confidenceLabel({ confidence: 87, words: "High" })).toBe("87 out of 100, High");
    expect(confidenceLabel({ confidence: 0, words: "Low" })).toBe("0 out of 100, Low");
  });
});

describe("confirmBlockedReason", () => {
  it("needs a client and a whole number of copies from 1 to 20", () => {
    expect(confirmBlockedReason("", "1", false)).toMatch(/client/);
    expect(confirmBlockedReason("9001", "0", false)).toMatch(/1 to 20/);
    expect(confirmBlockedReason("9001", "21", false)).toMatch(/1 to 20/);
    expect(confirmBlockedReason("9001", "1.5", false)).toMatch(/whole number/);
    expect(confirmBlockedReason("9001", "", false)).toMatch(/whole number/);
  });
  it("is clear for 1 to 20 and off while working", () => {
    expect(confirmBlockedReason("9001", "2", false)).toBe("");
    expect(confirmBlockedReason("9001", "20", false)).toBe("");
    expect(confirmBlockedReason("9001", "2", true)).not.toBe("");
  });
});

describe("the copies warning", () => {
  it("is silent up to two and speaks above", () => {
    expect(confirmCopiesWarning("1")).toBe("");
    expect(confirmCopiesWarning("2")).toBe("");
    expect(confirmCopiesWarning("3")).toMatch(/3 copies is more than usual/);
  });
});

describe("candidates", () => {
  it("shows the first candidate as the best guess and says when two are close", () => {
    const ambiguous = stubCandidates("stub-scan-3");
    expect(bestGuess(ambiguous)?.ambiguous).toBe(true);
    expect(ambiguityNote(bestGuess(ambiguous))).toMatch(/Two clients are close/);
    expect(ambiguityNote(bestGuess(stubCandidates("stub-scan-2")))).toBe("");
  });
  it("has no best guess when nothing could be estimated", () => {
    expect(bestGuess(stubCandidates("stub-scan-1"))).toBeUndefined();
    expect(bestGuess(undefined)).toBeUndefined();
  });
  it("names an order as one that tells Case flow", () => {
    expect(kindLabel("order")).toMatch(/Case flow/);
    expect(kindLabel("other")).toBe("");
  });
  it("lists for a client only the scans where that client is a candidate", () => {
    expect(stubClientScans("9001").map((s) => s.id)).toEqual(["stub-scan-2"]);
    expect(stubClientScans("9003").map((s) => s.id)).toEqual(["stub-scan-6"]);
    expect(stubClientScans("1")).toEqual([]);
  });
});

describe("the stub confirm", () => {
  it("passes the copies through, never bills, and asks twice for an order when an emailed reply is filed", () => {
    const first = stubConfirm("stub-x", "9003", 3, "order", false);
    expect(first.copies).toBe(3);
    expect(first.message).toMatch(/Not billed/);
    expect(first.case_flow?.needs_confirm).toBe(true);
    expect(stubConfirm("stub-x", "9003", 3, "order", true).case_flow?.ok).toBe(true);
    expect(stubConfirm("stub-y", "9001", 1, "other", false).case_flow).toBeNull();
  });
});
