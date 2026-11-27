import { describe, expect, it } from "vitest";
import { buildAnTodo, buildMarkedTodos, sentenceAround } from "./anTodo";

const NOW = new Date("2026-10-21T10:00:00Z");

describe("buildAnTodo", () => {
  it("takes the title from the sentence and the due date from the detected date", () => {
    const note = "Spoke to client. Need to file the C100 on 30 October 2026. Client agreed.";
    const draft = buildAnTodo(note, { date: "2026-10-30", matchedText: "30 October 2026" }, NOW);
    expect(draft).toEqual({ title: "Need to file the C100", due: "2026-10-30", dueHasTime: false });
  });

  it("carries a time when the sentence gives one on the same date", () => {
    const draft = buildAnTodo("Hearing listed for 3 November 2026 at 2pm.", { date: "2026-11-03", matchedText: "3 November 2026 at 2pm" }, NOW);
    expect(draft?.dueHasTime).toBe(true);
    expect(draft?.due).toBe("2026-11-03T14:00:00.000Z");
  });

  it("offers nothing for a date already past", () => {
    expect(buildAnTodo("Order dated 1 October 2026.", { date: "2026-10-01", matchedText: "1 October 2026" }, NOW)).toBeNull();
  });

  it("falls back to a plain title when the sentence cannot be found", () => {
    expect(buildAnTodo("x", { date: "2026-10-30", matchedText: "30 October" }, NOW)?.title).toBe("Follow up from attendance note");
  });
});

describe("sentenceAround", () => {
  it("returns the line the date is on", () => {
    expect(sentenceAround("First line\nCall court on Friday\nLast", "Friday")).toBe("Call court on Friday");
  });
});

describe("buildMarkedTodos", () => {
  const NOW2 = new Date("2026-10-21T10:00:00Z");

  it("offers the rest of a To do line, split at semicolons, with no date needed", () => {
    const got = buildMarkedTodos("Spoke to client about the order. To do: send the bundle; chase the court for a reply.", NOW2);
    expect(got.map((t) => t.title)).toEqual(["send the bundle", "chase the court for a reply"]);
    expect(got.every((t) => t.due === null)).toBe(true);
  });

  it("offers each bullet or numbered line straight after the marker, and stops at the first line that is not one", () => {
    const note = "Attended.\nTo do\n- ring the court\n- email counsel\n2. print the bundle\n\nNothing else to do today.";
    expect(buildMarkedTodos(note, NOW2).map((t) => t.title)).toEqual(["ring the court", "email counsel", "print the bundle"]);
  });

  it("takes a due date from the item itself and leaves the date words out of the title", () => {
    const got = buildMarkedTodos("todo: ring the court on 30 October 2026", NOW2);
    expect(got).toEqual([{ key: "ring the court", title: "ring the court", due: "2026-10-30", dueHasTime: false }]);
  });

  it("keeps an item whose date is already past, undated and whole", () => {
    const got = buildMarkedTodos("To do: reply to the letter of 1 October 2026", NOW2);
    expect(got).toHaveLength(1);
    expect(got[0].due).toBeNull();
    expect(got[0].title).toContain("1 October 2026");
  });

  it("does not read ordinary prose as a list", () => {
    expect(buildMarkedTodos("He has nothing to do with the matter. I asked what to do next.", NOW2)).toEqual([]);
    expect(buildMarkedTodos("To do with the children's school, nothing agreed.", NOW2)).toEqual([]);
    expect(buildMarkedTodos("", NOW2)).toEqual([]);
  });

  it("accepts todo, to-do and a second marker, drops duplicates and caps the list", () => {
    expect(buildMarkedTodos("To-do: call client\nTodo - call client; file form", NOW2).map((t) => t.title)).toEqual(["call client", "file form"]);
    const many = "To do: " + Array.from({ length: 15 }, (_, i) => `task number ${i + 1}`).join("; ");
    expect(buildMarkedTodos(many, NOW2)).toHaveLength(10);
  });
});
