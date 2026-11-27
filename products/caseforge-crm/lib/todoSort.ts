
import type { Todo } from "./todos";

export type TodoSort = "due_soonest" | "due_latest" | "important" | "newest" | "oldest" | "az" | "za";

export const SORT_LABELS: Record<TodoSort, string> = {
  due_soonest: "Due soonest",
  due_latest: "Due latest",
  important: "Important first",
  newest: "Newest first",
  oldest: "Oldest first",
  az: "A to Z",
  za: "Z to A",
};

export function matchesSearch(t: Todo, search: string): boolean {
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const hay = [t.title, t.notes, t.client_name ?? ""].join("\n").toLowerCase();
  return words.every((w) => hay.includes(w));
}

const byCreated = (a: Todo, b: Todo): number => Date.parse(a.created_utc) - Date.parse(b.created_utc);

function dueMs(t: Todo): number | null {
  if (!t.due_utc) return null;
  const ms = Date.parse(t.due_utc);
  return Number.isNaN(ms) ? null : ms;
}

function byDue(dir: 1 | -1) {
  return (a: Todo, b: Todo): number => {
    const x = dueMs(a);
    const y = dueMs(b);
    if (x !== null && y !== null && x !== y) return (x - y) * dir;
    if (x === null && y !== null) return 1;
    if (y === null && x !== null) return -1;
    return byCreated(b, a);
  };
}

const byTitle = (a: Todo, b: Todo): number => a.title.localeCompare(b.title, "en-GB", { sensitivity: "base", numeric: true });

export function sortTodos(items: Todo[], sort: TodoSort): Todo[] {
  const copy = [...items];
  switch (sort) {
    case "due_soonest":
      return copy.sort(byDue(1));
    case "due_latest":
      return copy.sort(byDue(-1));
    case "important":

      return copy.sort((a, b) => Number(b.starred) - Number(a.starred) || byDue(1)(a, b));
    case "newest":
      return copy.sort((a, b) => byCreated(b, a));
    case "oldest":
      return copy.sort(byCreated);
    case "az":
      return copy.sort(byTitle);
    case "za":
      return copy.sort((a, b) => byTitle(b, a));
  }
}

export function filterAndSort(items: Todo[], search: string, sort: TodoSort): Todo[] {
  return sortTodos(
    items.filter((t) => matchesSearch(t, search)),
    sort,
  );
}
