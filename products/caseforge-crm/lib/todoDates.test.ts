import { describe, expect, it } from "vitest";
import { isPastDue, offerableDue, parseTodoText } from "./todoDates";

const NOW = new Date("2026-09-25T12:00:00+01:00");

describe("parseTodoText", () => {
  it("takes a weekday and a time out of the task, Todoist style", () => {
    const parsed = parseTodoText("ring the court friday 2pm", NOW);
    expect(parsed.title).toBe("ring the court");
    expect(parsed.hasTime).toBe(true);
    expect(new Date(parsed.due as string).toISOString()).toBe("2026-09-25T13:00:00.000Z");
    expect(parsed.matchedText.toLowerCase()).toContain("friday");
  });

  it("gives a plain date, not an instant, when no time was written", () => {
    expect(parseTodoText("send bundle tomorrow", NOW)).toMatchObject({ title: "send bundle", due: "2026-09-26", hasTime: false });
    expect(parseTodoText("chase order 30 September", NOW)).toMatchObject({ title: "chase order", due: "2026-09-30", hasTime: false });
    expect(parseTodoText("call back on Monday", NOW)).toMatchObject({ title: "call back", due: "2026-09-28", hasTime: false });
  });

  it("reads a UK dotted date and a relative span", () => {
    expect(parseTodoText("hearing prep 4.11.26", NOW).due).toBe("2026-11-04");
    expect(parseTodoText("follow up in 3 days", NOW)).toMatchObject({ title: "follow up", due: "2026-09-28" });
  });

  it("drops a dangling 'on', 'by' or 'at' left behind by the date", () => {
    expect(parseTodoText("file the order by 30 September", NOW).title).toBe("file the order");
    expect(parseTodoText("on 30 September file the order", NOW).title).toBe("file the order");
  });

  it("leaves a task with no date alone, and never treats the word now as one", () => {
    expect(parseTodoText("ask counsel about the brief", NOW)).toEqual({ title: "ask counsel about the brief", due: null, hasTime: false, matchedText: "" });
    expect(parseTodoText("chase counsel now", NOW).due).toBeNull();
    expect(parseTodoText("she may sign the form", NOW).due).toBeNull();
    expect(parseTodoText("", NOW).due).toBeNull();
  });

  it("keeps the whole text as the title when the date is all there is", () => {
    expect(parseTodoText("tomorrow", NOW)).toMatchObject({ title: "tomorrow", due: "2026-09-26" });
  });
});

describe("dates that have already passed are not offered", () => {

  const NOW = new Date("2026-09-26T09:00:00Z");

  it("treats an earlier day, or an earlier time today, as past, and today or later as not", () => {
    expect(isPastDue("2026-08-28", false, NOW)).toBe(true);
    expect(isPastDue("2026-09-25", false, NOW)).toBe(true);
    expect(isPastDue("2026-09-26", false, NOW)).toBe(false);
    expect(isPastDue("2026-10-01", false, NOW)).toBe(false);
    expect(isPastDue("2026-09-26T08:00:00.000Z", true, NOW)).toBe(true);
    expect(isPastDue("2026-09-26T15:00:00.000Z", true, NOW)).toBe(false);
  });

  it("the owner's example: a date the task is about is not offered as its due date", () => {
    const parsed = parseTodoText("print the order of 28.08.26", NOW);
    expect(parsed.due).toBe("2026-08-28");
    expect(offerableDue(parsed, NOW)).toBeNull();
  });

  it("a future date is offered, and text with no date offers nothing", () => {
    expect(offerableDue(parseTodoText("ring the court friday 2pm", NOW), NOW)?.hasTime).toBe(true);
    expect(offerableDue(parseTodoText("ring the court on 30.09.26", NOW), NOW)?.due).toBe("2026-09-30");
    expect(offerableDue(parseTodoText("ring the court", NOW), NOW)).toBeNull();
  });
});
