
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const CSS = readFileSync(fileURLToPath(new URL("../app/glyphs.css", import.meta.url)), "utf8");
const FORM = readFileSync(fileURLToPath(new URL("./AttendanceNoteForm.tsx", import.meta.url)), "utf8");

function rule(selector: string): string {
  const start = CSS.indexOf(`${selector} {`);
  expect(start, selector).toBeGreaterThan(-1);
  return CSS.slice(start, CSS.indexOf("}", start));
}

describe("the Attendance Notes divider", () => {
  it("is under the buttons and no longer under the whole form", () => {
    expect(rule(".an-form")).not.toContain("border-bottom");
    expect(rule(".an-form .an-form-actions")).toContain("border-bottom: 1px solid var(--border)");
  });

  it("the recent notes list renders after the buttons inside the form, so the line is between them", () => {
    expect(FORM.indexOf('className="an-form-actions"')).toBeGreaterThan(-1);
    expect(FORM.indexOf("<RecentAttendanceNotes")).toBeGreaterThan(FORM.indexOf('className="an-form-actions"'));
  });
});
