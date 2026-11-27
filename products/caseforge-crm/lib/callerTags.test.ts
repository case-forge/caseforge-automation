import { describe, expect, it } from "vitest";
import { callerTagsOf } from "./callerTags";

describe("callerTagsOf", () => {
  it("shows nothing without flags", () => {
    expect(callerTagsOf(undefined)).toEqual([]);
    expect(callerTagsOf(null)).toEqual([]);
    expect(callerTagsOf({})).toEqual([]);
  });

  it("marks a persistent client caller as PC", () => {
    expect(callerTagsOf({ persistent_caller: true })).toEqual([{ code: "PC", label: "Frequent caller", kind: "client" }]);
  });

  it("marks a persistent Respondent caller as PC(R)", () => {
    expect(callerTagsOf({ persistent_caller_respondent: true })).toEqual([
      { code: "PC(R)", label: "Frequent caller (Opponent)", kind: "opponent" },
    ]);
  });

  it("shows both in a fixed order when both are set", () => {
    const codes = callerTagsOf({ persistent_caller_respondent: true, persistent_caller: true }).map((t) => t.code);
    expect(codes).toEqual(["PC", "PC(R)"]);
  });

  it("ignores false and unrelated flags", () => {
    expect(callerTagsOf({ persistent_caller: false, flagged: true, starred: true })).toEqual([]);
  });
});
