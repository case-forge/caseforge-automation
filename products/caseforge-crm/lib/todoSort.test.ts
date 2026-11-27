import { describe, expect, it } from "vitest";
import { filterAndSort, matchesSearch, sortTodos } from "./todoSort";
import type { Todo } from "./todos";

function todo(over: Partial<Todo>): Todo {
  return {
    todo_id: "t",
    title: "Task",
    notes: "",
    matter_id: null,
    client_name: null,
    created_by: "Alex",
    due_utc: null,
    due_has_time: false,
    starred: false,
    my_day_date: null,
    on_my_day_today: false,
    is_done: false,
    is_overdue: false,
    source: "",
    created_utc: "2026-10-01T09:00:00Z",
    updated_utc: "2026-10-01T09:00:00Z",
    done_utc: null,
    done_by: "",
    ...over,
  };
}

const a = todo({ todo_id: "a", title: "banana", due_utc: "2026-10-25T00:00:00Z", created_utc: "2026-10-03T00:00:00Z" });
const b = todo({ todo_id: "b", title: "Apple", due_utc: "2026-10-22T00:00:00Z", created_utc: "2026-10-01T00:00:00Z", client_name: "Jane Doe" });
const c = todo({ todo_id: "c", title: "cherry", created_utc: "2026-10-02T00:00:00Z" });
const ids = (xs: Todo[]) => xs.map((t) => t.todo_id).join("");

describe("sortTodos", () => {
  it("sorts A to Z ignoring case, and Z to A", () => {
    expect(ids(sortTodos([a, b, c], "az"))).toBe("bac");
    expect(ids(sortTodos([a, b, c], "za"))).toBe("cab");
  });
  it("puts tasks with no due date last in both due orders", () => {
    expect(ids(sortTodos([c, a, b], "due_soonest"))).toBe("bac");
    expect(ids(sortTodos([c, a, b], "due_latest"))).toBe("abc");
  });
  it("sorts by when the task was created", () => {
    expect(ids(sortTodos([a, b, c], "newest"))).toBe("acb");
    expect(ids(sortTodos([a, b, c], "oldest"))).toBe("bca");
  });
  it("puts starred tasks first, then the soonest due", () => {
    const star = todo({ todo_id: "s", title: "starred", starred: true, created_utc: "2026-10-04T00:00:00Z" });
    expect(ids(sortTodos([c, a, star, b], "important"))).toBe("sbac");
  });
  it("shows undated tasks newest first under either due order, so the choice always changes the list", () => {
    const x = todo({ todo_id: "x", created_utc: "2026-10-05T00:00:00Z" });
    const y = todo({ todo_id: "y", created_utc: "2026-10-06T00:00:00Z" });
    expect(ids(sortTodos([x, y], "due_soonest"))).toBe("yx");
    expect(ids(sortTodos([y, x], "due_latest"))).toBe("yx");
  });
  it("never mutates the input", () => {
    const input = [c, a, b];
    sortTodos(input, "az");
    expect(ids(input)).toBe("cab");
  });
});

describe("matchesSearch", () => {
  it("needs every word, across title and client, in any case", () => {
    expect(matchesSearch(b, "apple jane")).toBe(true);
    expect(matchesSearch(b, "APPLE doe")).toBe(true);
    expect(matchesSearch(b, "apple sam")).toBe(false);
    expect(matchesSearch(c, "cherry")).toBe(true);
  });
  it("matches everything when empty", () => {
    expect(matchesSearch(a, "   ")).toBe(true);
  });
  it("filters then sorts", () => {
    expect(ids(filterAndSort([a, b, c], "an", "az"))).toBe("ba");
  });
});

describe("the toolbar", () => {
  it("offers every sort once, opens on Due soonest, sorts from an A to Z icon button, and has a Print button that prints the page", async () => {
    const { readFileSync } = await import("node:fs");
    const src = readFileSync(new URL("../components/TodoToolbar.tsx", import.meta.url), "utf8");
    expect(src).toContain('useState<TodoSort>("due_soonest")');
    expect(src).toContain("IconSortAZ");
    expect(readFileSync(new URL("../components/TodoParts.tsx", import.meta.url), "utf8")).toContain("window.print()");
    const { SORT_LABELS } = await import("./todoSort");
    for (const key of Object.keys(SORT_LABELS)) expect(src.match(new RegExp(`"${key}"`, "g"))?.length ?? 0).toBeGreaterThan(0);
  });
});
