
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./AttendanceNoteForm.tsx", import.meta.url)), "utf8");

describe("AttendanceNoteForm.tsx server copy", () => {
  it("restores from the server on opening a client", () => {
    expect(SOURCE).toContain("restoreIfLocalEmpty(matterId)");
    expect(SOURCE).toContain("setDrafts(restored.drafts)");
  });

  it("pushes changes, and flushes when the form closes", () => {
    expect(SOURCE).toContain("schedulePush(matterId)");
    expect(SOURCE).toContain("flushPush(matterId)");
  });

  it("puts note type and who it is with on one row, before the time", () => {
    const row = SOURCE.slice(SOURCE.indexOf('<div className="an-form-callers-row">'), SOURCE.indexOf("<textarea"));
    const kindAt = row.indexOf('name="an-kind"');
    const callerAt = row.indexOf('name="an-caller"');
    const otherAt = row.indexOf('className="an-form-other"');
    const timeAt = row.indexOf('className="an-form-time"');
    expect(kindAt).toBeGreaterThan(-1);
    expect(kindAt < callerAt && callerAt < otherAt && otherAt < timeAt).toBe(true);
  });

  it("does not push until the restore attempt has finished", () => {
    const pushEffect = SOURCE.slice(SOURCE.indexOf("schedulePush(matterId)") - 160, SOURCE.indexOf("schedulePush(matterId)") + 40);
    expect(pushEffect).toContain("restoreDone.current");
  });

  it("offers three note types, labels the who-choice Party, and has no letter type list or envelope offer", () => {
    expect(SOURCE).toContain("ATTENDANCE_CREATE_KINDS");
    expect(SOURCE).toContain("ATTENDANCE_WHO_LEGEND");
    expect(SOURCE).not.toContain("an-doc-kind");
    expect(SOURCE).not.toContain("EnvelopeOffer");
    expect(SOURCE).not.toContain("LAA-Billing");
  });

  it("lets pages set the time but never the time set the pages", () => {
    expect(SOURCE).toContain("minutesForPages(Number(clean), minutesPerPage)");
    expect(SOURCE).not.toContain("pagesForMinutes");
    const changeTime = SOURCE.slice(SOURCE.indexOf("function changeTime"), SOURCE.indexOf("function changePages"));
    expect(changeTime).not.toContain("setPagesText");
  });

  it("labels Pages in the shared label style, beside the party or Doc type and not in the time group", () => {
    expect(SOURCE).toContain(">Pages</span>");
    expect(SOURCE).toContain('name="an-pages"');
    const time = SOURCE.slice(SOURCE.indexOf('className="an-form-time"'), SOURCE.indexOf('className="an-form-time-toggle"'));
    expect(time).not.toContain('name="an-pages"');
  });
});

describe("tasks listed after To do", () => {
  const source = readFileSync(fileURLToPath(new URL("./AttendanceNoteForm.tsx", import.meta.url)), "utf8");
  it("get their own offer rows, apart from the hearing and the dated To do", () => {
    expect(source).toContain("buildMarkedTodos(noteText)");
    expect(source).toContain("markedTodos.map((item)");

    expect(source).toContain("setMarkedDismissed");
    expect(source).toContain("setMarkedAdded");
    expect(source).toContain("draftCoveredByList");
  });
});
