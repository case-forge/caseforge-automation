import { describe, expect, it } from "vitest";
import {
  duplicateMessage,
  duplicateTarget,
  findDuplicateHearings,
  hearingState,
  validateMove,
  vacateBody,
} from "./hearingActions";
import { isVacated, requestLabel, statusLabel, vacatedSummary } from "./hearings";
import type { Hearing } from "./hearings";
import { stubCourtDecision, stubRequestFromCourt, stubResetHearings, stubVacateHearing, stubCreateHearing } from "./stubHearings";

function hearing(over: Partial<Hearing> = {}): Hearing {
  return {
    hearing_id: 1,
    matter_id: 7,
    client_name: null,
    case_ref: "ZW26F00000",
    hearing_date: "2026-09-25",
    hearing_time: "10:00",
    duration_minutes: 60,
    hearing_type: "FHDRA",
    order_types: "CAO",
    is_final: false,
    court: "Example Family Court",
    mode: "",
    join_url: "",
    applicant: "",
    respondent: "",
    status: "scheduled",
    review_state: "ok",
    review_reason: "",
    confidence: null,
    source_kind: "manual",
    source_subject: "",
    source_received_utc: "",
    source_web_link: "",
    notes: "",
    created_utc: "",
    updated_utc: "",
    updated_by: "",
    ...over,
  };
}

describe("one model of a hearing's state", () => {
  it("is scheduled, requested (red) or vacated; cancelled is just the old word for vacated", () => {
    expect(hearingState(hearing())).toBe("scheduled");
    expect(hearingState(hearing({ request_state: "vacation_requested" }))).toBe("vacation_requested");
    expect(hearingState(hearing({ request_state: "hybrid_requested" }))).toBe("hybrid_requested");
    expect(hearingState(hearing({ status: "vacated" }))).toBe("vacated");
    expect(hearingState(hearing({ status: "cancelled" }))).toBe("vacated");
    expect(isVacated({ status: "cancelled" })).toBe(true);
    expect(statusLabel("cancelled")).toBe("Vacated");
  });

  it("words a request and a vacated hearing without colour alone", () => {
    expect(requestLabel(hearing({ request_state: "vacation_requested" }))).toBe("Vacation requested");
    expect(requestLabel(hearing({ request_state: "hybrid_requested" }))).toBe("Hybrid requested");
    expect(requestLabel(hearing())).toBe("");

    expect(requestLabel(hearing({ status: "vacated", request_state: "vacation_requested" }))).toBe("");
    expect(vacatedSummary(hearing())).toBe("");
    expect(vacatedSummary(hearing({ status: "vacated", vacate_kind: "no_longer_acting" }))).toContain("no longer acting");
    expect(
      vacatedSummary(hearing({ status: "vacated", vacate_kind: "moved", replaced_by: { hearing_id: 2, hearing_date: "2026-09-25", hearing_time: "14:00" } })),
    ).toMatch(/^Moved to .*2:00pm$/);
  });
});

describe("a move", () => {
  const original = { hearing_date: "2026-09-25", hearing_time: "10:00" };
  it("needs a real, different date or time", () => {
    expect(validateMove(original, { hearing_date: "", hearing_time: "14:00" })).toMatch(/new date/);
    expect(validateMove(original, { hearing_date: "2026-02-31", hearing_time: "14:00" })).toMatch(/real date/);
    expect(validateMove(original, { hearing_date: "2026-09-25", hearing_time: "25:00" })).toMatch(/HH:MM/);
    expect(validateMove(original, { hearing_date: "2026-09-25", hearing_time: "10:00" })).toMatch(/same date and time/);

    expect(validateMove(original, { hearing_date: "2026-09-25", hearing_time: "14:00" })).toBeNull();
    expect(validateMove(original, { hearing_date: "2026-10-02", hearing_time: "10:00" })).toBeNull();
  });

  it("sends the new date and time only for a move, and the reason only when given", () => {
    expect(vacateBody(5, "moved", " Relisted ", { hearing_date: "2026-09-25", hearing_time: "14:00" })).toEqual({
      hearing_id: 5,
      kind: "moved",
      reason: "Relisted",
      replacement: { hearing_date: "2026-09-25", hearing_time: "14:00" },
    });
    expect(vacateBody(5, "no_longer_acting", "")).toEqual({ hearing_id: 5, kind: "no_longer_acting" });
    expect(vacateBody(5, "moved", "", { hearing_date: "2026-10-02", hearing_time: " " }).replacement).toEqual({ hearing_date: "2026-10-02" });
  });
});

describe("live duplicate detection while typing the New hearing form", () => {
  const existing = [
    hearing({ hearing_id: 1, hearing_time: "10:00" }),
    hearing({ hearing_id: 2, case_ref: "ZW26F99999" }),
    hearing({ hearing_id: 3, hearing_date: "2026-09-26" }),
  ];
  const form = (over: object) => ({ case_ref: "ZW26F00000", matter_id: "", hearing_date: "2026-09-25", hearing_time: "10:00", ...over });

  it("finds the same case on the same day at the same time", () => {
    const found = findDuplicateHearings(existing, form({ case_ref: " zw26f00000 " }));
    expect(found.exact?.hearing_id).toBe(1);
    expect(duplicateMessage(found)).toMatch(/date and time/);
    expect(duplicateTarget(found)?.hearing_id).toBe(1);
  });

  it("offers the nearby hearing as a probable move, and not one hours away", () => {
    const near = findDuplicateHearings(existing, form({ hearing_time: "11:30" }));
    expect(near.exact).toBeNull();
    expect(near.nearby.map((h) => h.hearing_id)).toEqual([1]);
    expect(duplicateMessage(near)).toMatch(/moved/);
    expect(findDuplicateHearings(existing, form({ hearing_time: "16:30" })).nearby).toEqual([]);
  });

  it("matches on the client when there is no case number, and waits for a real date", () => {
    expect(findDuplicateHearings(existing, form({ case_ref: "", matter_id: "7" })).exact?.hearing_id).toBe(1);
    expect(findDuplicateHearings(existing, form({ case_ref: "", matter_id: "8" })).exact).toBeNull();
    expect(findDuplicateHearings(existing, form({ case_ref: "", matter_id: "" }))).toEqual({ exact: null, nearby: [] });
    expect(findDuplicateHearings(existing, form({ hearing_date: "2026-09-2" }))).toEqual({ exact: null, nearby: [] });
  });

  it("with no time typed yet, any hearing that day is offered", () => {
    const found = findDuplicateHearings(existing, form({ hearing_time: "" }));
    expect(found.exact).toBeNull();
    expect(found.nearby.map((h) => h.hearing_id)).toEqual([1]);
  });

  it("ignores vacated and dismissed hearings", () => {
    const list = [hearing({ status: "vacated" }), hearing({ hearing_id: 4, review_state: "dismissed" }), hearing({ hearing_id: 5, status: "cancelled" })];
    expect(findDuplicateHearings(list, form({}))).toEqual({ exact: null, nearby: [] });
  });
});

describe("the demo store follows the same rules as the server", () => {
  it("a move vacates the old hearing and creates the linked replacement; a request goes red then the court answers", () => {
    stubResetHearings();
    const created = stubCreateHearing(
      { case_ref: "ZZ26F00001", hearing_date: "2026-09-25", hearing_time: "10:00", court: "Example Family Court", order_types: "NMO" },
      "Sam",
    );
    const asked = stubRequestFromCourt(created.hearing_id, "hybrid", ["Remote attendance."], "", "Sam");
    expect(asked.hearing.request_state).toBe("hybrid_requested");
    expect(asked.form).toBe("FP2");
    expect(stubCourtDecision(created.hearing_id, true, "Sam").mode).toBe("hybrid");

    const moved = stubVacateHearing(created.hearing_id, "moved", "Relisted", { hearing_date: "2026-09-25", hearing_time: "14:00" }, "Sam");
    expect(moved.hearing.status).toBe("vacated");
    expect(moved.replacement?.hearing_time).toBe("14:00");
    expect(moved.replacement?.court).toBe("Example Family Court");
    expect(moved.hearing.replaced_by?.hearing_id).toBe(moved.replacement?.hearing_id);
    expect(() => stubVacateHearing(created.hearing_id, "other", "", undefined, "Sam")).toThrow(/already vacated/);
    expect(() => stubCourtDecision(moved.replacement!.hearing_id, true, "Sam")).toThrow(/no request/);
  });
});
