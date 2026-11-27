import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(new URL("./TodoParts.tsx", import.meta.url), "utf8");

describe("TodoParts.tsx", () => {
  it("asks for no name to add, finish, star or delete a task: the firm shares one identity", () => {
    expect(SOURCE).not.toContain("Type your name first");
  });
  it("has a Delete button, the star and My Day controls, and the done tick that reopens a task", () => {
    expect(SOURCE).toContain('title="Delete"');
    expect(SOURCE).toContain('title="Important"');
    expect(SOURCE).toContain('title="My Day"');
    expect(SOURCE).toContain("Reopen:");
  });
  it("lets a task's text be edited in place: a pencil button or a double-click, Enter saves, Escape cancels", () => {
    expect(SOURCE).toContain('title="Edit"');
    expect(SOURCE).toContain("onDoubleClick={startEdit}");
    expect(SOURCE).toContain("updateTodo(todo.todo_id, { title })");
    expect(SOURCE).toContain('e.key === "Escape"');
  });
  it("makes the pencil a toggle: pressing it while editing saves and closes (the mouse-down keeps the field from blurring first)", () => {
    expect(SOURCE).toContain("onMouseDown={(e) => e.preventDefault()}");
    expect(SOURCE).toContain("editing ? void saveEdit() : startEdit()");
  });
  it("offers an icon-only Email client button only on a task tied to a client, which becomes Open draft once a draft exists", () => {
    expect(SOURCE).toContain('title="Email client"');
    expect(SOURCE).toContain("IconEnvelope");
    expect(SOURCE).toContain('title="Open draft"');
    expect(SOURCE).toContain("todo.matter_id != null");
    expect(SOURCE).toContain("emailClientTodo(todo.todo_id)");
    expect(SOURCE).toContain("safeLink(todo.draft_link)");
  });
});
