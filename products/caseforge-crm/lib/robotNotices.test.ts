import { describe, expect, it } from "vitest";
import { BELL_DAYS } from "./notificationRules";
import { ageLabel, capRobotNotices, noticeCode, robotButtonLabel, splitNotices, tabForNotice, unseenBlocks } from "./robotNotices";
import type { RobotNotice } from "./robotNotices";
import { stubRobotNotices } from "./stubRobot";

describe("ageLabel", () => {
  const now = new Date("2026-09-25T12:00:00Z");
  it("reads in minutes, hours and days", () => {
    expect(ageLabel("2026-09-25T11:59:40Z", now)).toBe("just now");
    expect(ageLabel("2026-09-25T11:40:00Z", now)).toBe("20 min ago");
    expect(ageLabel("2026-09-25T09:00:00Z", now)).toBe("3 h ago");
    expect(ageLabel("2026-09-22T12:00:00Z", now)).toBe("3 d ago");
  });
  it("is blank for a bad date and never negative for a future one", () => {
    expect(ageLabel("nonsense", now)).toBe("");
    expect(ageLabel("2026-09-25T12:30:00Z", now)).toBe("just now");
  });
});

describe("robotButtonLabel", () => {
  it("puts the count in words", () => {
    expect(robotButtonLabel(0)).toBe("Automation notices, none waiting");
    expect(robotButtonLabel(1)).toBe("Automation notices, 1 needs a person");
    expect(robotButtonLabel(3)).toBe("Automation notices, 3 need a person");
  });
});

describe("tabForNotice", () => {
  it("sends the attendance-note notices to the Attendance notes tab and leaves the rest alone", () => {
    expect(tabForNotice("attendance_note_failed")).toBe("attendance");
    expect(tabForNotice("attendance_note_unsorted")).toBe("attendance");
    expect(tabForNotice("attendance_note_bundle_pages")).toBe("attendance");
    expect(tabForNotice("folder_no_record")).toBeUndefined();
    expect(tabForNotice("case_moved")).toBe("caseflow");
  });
});

describe("a case-moved notice added by the demo", () => {
  it("is added newest first with an id and a time", async () => {
    const { stubAddRobotNotice, stubDismissRobotNotice } = await import("./stubRobot");
    const before = stubAddRobotNotice({ kind: "case_moved", title: "Case moved to another caseworker", detail: "Jordan moved a folder.", matter_id: "9100", client_name: "Test Person" });
    expect(before.items[0].kind).toBe("case_moved");
    expect(before.items[0].notice_id).toMatch(/^stub-robot-/);
    expect(before.items[0].created_utc).toMatch(/^\d{4}-/);
    expect(stubDismissRobotNotice(before.items[0].notice_id).items.some((n) => n.notice_id === before.items[0].notice_id)).toBe(false);
  });
});

describe("capRobotNotices", () => {
  const now = new Date("2026-10-25T12:00:00Z");
  const notice = (id: string, created_utc: string): RobotNotice => ({
    notice_id: id, kind: "x", title: id, detail: "", matter_id: "", client_name: "", created_utc,
  });
  it("shows the last BELL_DAYS days and counts the rest", () => {
    const items = [
      notice("new", "2026-10-25T11:00:00Z"),
      notice("edge", new Date(now.getTime() - BELL_DAYS * 86_400_000).toISOString()),
      notice("old", "2026-10-20T12:00:00Z"),
      notice("older", "2026-10-01T12:00:00Z"),
    ];
    const { shown, more } = capRobotNotices(items, now);
    expect(shown.map((n) => n.notice_id)).toEqual(["new", "edge"]);
    expect(more).toBe(2);
  });
  it("never hides a notice whose date does not parse", () => {
    expect(capRobotNotices([notice("bad", "nope")], now)).toEqual({ shown: [expect.objectContaining({ notice_id: "bad" })], more: 0 });
  });
  it("has no rest when everything is recent", () => {
    expect(capRobotNotices([], now)).toEqual({ shown: [], more: 0 });
  });
  it("works on the stub data, which carries older notices", () => {
    const { shown, more } = capRobotNotices(stubRobotNotices().items);
    expect(more).toBe(2);
    expect(shown.length).toBe(5);
  });
});

describe("Case flow blocks in the header", () => {
  const n = (kind: string, id: string, title = "t"): RobotNotice => ({ notice_id: id, kind, title, detail: "", matter_id: "1", client_name: "A", created_utc: "2026-11-22T10:00:00Z" });

  it("splits Case flow blocks from every other automation notice", () => {
    const { blocked, other } = splitNotices([n("caseflow_step_blocked", "a"), n("caseflow_backlog", "b"), n("attendance_note_failed", "c"), n("job_blocked", "d")]);
    expect(blocked.map((x) => x.notice_id)).toEqual(["a", "b", "d"]);
    expect(other.map((x) => x.notice_id)).toEqual(["c"]);
  });

  it("reads the code from the title and nothing else", () => {
    expect(noticeCode("Case flow is stuck at the email step (CF-STMT-02)")).toBe("CF-STMT-02");
    expect(noticeCode("A signed document has no client attached (JOB-SIGN-01)")).toBe("JOB-SIGN-01");
    expect(noticeCode("Attendance note not filed")).toBe("");
    expect(noticeCode("Mentions CF-STMT-02 but not in brackets")).toBe("");
  });

  it("shows a popup only for a notice id not shown to this person before", () => {
    const blocked = [n("caseflow_step_blocked", "a"), n("caseflow_step_blocked", "b")];
    expect(unseenBlocks(blocked, ["a"]).map((x) => x.notice_id)).toEqual(["b"]);
    expect(unseenBlocks(blocked, ["a", "b"])).toEqual([]);
  });

  it("opens the Case flow tab for a blocked step", () => {
    expect(tabForNotice("caseflow_step_blocked")).toBe("caseflow");
  });
});
