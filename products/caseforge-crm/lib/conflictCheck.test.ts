import { describe, expect, it } from "vitest";
import { BLANK_ANSWER } from "./caseReviewTypes";
import type { CaseReviewAnswer } from "./caseReviewTypes";
import { conflictNotice, markedCleared } from "./conflictCheck";
import type { ConflictCheck, ConflictMatch } from "./conflictCheck";

const cleared: Record<string, CaseReviewAnswer> = { s_conflict: { ...BLANK_ANSWER, value: "yes", initials: "AB", date: "2026-10-12" } };
const open: Record<string, CaseReviewAnswer> = {};

function check(over: Partial<ConflictCheck> = {}): ConflictCheck {
  return {
    matter_id: "603",
    run: true,
    run_utc: "2026-10-12T09:00:00Z",
    run_by: "Sam",
    stale: false,
    verdict: "clear",
    matches: [],
    held_back: 0,
    parties_checked: 1,
    compared: { clients: 10, parties: 10 },
    gaps: [],
    ...over,
  };
}

function match(strength: ConflictMatch["strength"]): ConflictMatch {
  return {
    direction: "opponent_is_client",
    strength,
    reasons: ["similar name"],
    this_is: "Respondent on this matter: A",
    that_is: "Client in another matter",
    other_name: "B",
    other_matter_id: "700",
    other_reference: "",
    other_client: "B",
    other_closed: false,
  };
}

describe("conflictNotice", () => {
  it("says nothing while the check is still loading", () => {
    expect(conflictNotice(null, open)).toBeNull();
  });

  it("warns when no check has been run, and raises it to an alert when the forms already say cleared", () => {
    const none = check({ run: false, verdict: "" });
    expect(conflictNotice(none, open)?.level).toBe("warn");
    expect(conflictNotice(none, cleared)?.level).toBe("alert");
  });

  it("alerts on a possible match and names a mismatch with a cleared form", () => {
    const found = check({ verdict: "review", matches: [match("strong"), match("weak")] });
    expect(conflictNotice(found, open)).toMatchObject({ level: "alert", headline: expect.stringContaining("1 possible match ") });
    expect(conflictNotice(found, cleared)?.lines.join(" ")).toContain("say the conflict check is cleared");
  });

  it("calls a stale clear result out of date, not clear", () => {
    expect(conflictNotice(check({ stale: true }), open)).toMatchObject({ level: "warn", headline: "This check is out of date." });
  });

  it("treats weak matches as information and keeps the data gaps", () => {
    const n = conflictNotice(check({ verdict: "weak", matches: [match("weak")], gaps: ["name alone"] }), cleared);
    expect(n).toMatchObject({ level: "info", lines: ["name alone"] });
  });

  it("is quiet and informational when clear with nothing missing, and a warning when a gap remains", () => {
    expect(conflictNotice(check(), cleared)).toMatchObject({ level: "info", headline: "No matches found." });
    expect(conflictNotice(check({ gaps: ["Only the client was checked."] }), cleared)?.level).toBe("warn");
  });
});

describe("markedCleared", () => {
  it("is true when either conflict row says yes, and not for no or n/a", () => {
    expect(markedCleared({ r_opening_conflict: { ...BLANK_ANSWER, value: "yes" } })).toBe(true);
    expect(markedCleared({ r_opening_conflict: { ...BLANK_ANSWER, value: "no" } })).toBe(false);
    expect(markedCleared({ r_opening_conflict: { ...BLANK_ANSWER, value: "na" } })).toBe(false);
  });
});
