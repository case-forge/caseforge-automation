import { describe, expect, it } from "vitest";
import { stubEmailClientTodo } from "./stubTodos";

describe("stubEmailClientTodo", () => {
  it("fakes a draft once for a client task and returns the same link on a second press", () => {
    const first = stubEmailClientTodo("stub-t1");
    expect("error" in first).toBe(false);
    if ("error" in first) return;
    expect(first.created).toBe(true);
    expect(first.draft_link).toMatch(/^https:\/\//);
    expect(first.todo.draft_link).toBe(first.draft_link);
    const again = stubEmailClientTodo("stub-t1");
    expect("error" in again ? true : again.created).toBe(false);
  });
  it("refuses a missing task", () => {
    expect(stubEmailClientTodo("nope")).toEqual({ error: "no such task: nope" });
  });
});
