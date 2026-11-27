
import type { Todo, TodoSummary } from "./todos";
import { DEMO_SECOND } from "./stubFirm";

const HOUR = 3_600_000;
let seq = 3;

function iso(ms: number): string {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function endOfDay(date: string): string {
  return iso(new Date(`${date}T23:59:00`).getTime());
}

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function base(over: Partial<Todo> & Pick<Todo, "todo_id" | "title">): Todo {
  const stamp = iso(Date.now());
  return {
    notes: "", matter_id: null, client_name: null, created_by: DEMO_SECOND, due_utc: null, due_has_time: false,
    starred: false, my_day_date: null, on_my_day_today: false, is_done: false, is_overdue: false, source: "manual",
    created_utc: stamp, updated_utc: stamp, done_utc: null, done_by: "", draft_link: "", ...over,
  };
}

const todos: (Todo & { deleted?: boolean })[] = [
  base({ todo_id: "stub-t1", title: "Ring the county court about the 1 September order", matter_id: 9001, client_name: "Stub Testperson", due_utc: iso(Date.now() - 3 * HOUR), due_has_time: true, starred: true }),
  base({ todo_id: "stub-t2", title: "Send the bundle to counsel", matter_id: 9001, client_name: "Stub Testperson", due_utc: iso(Date.now() + 50 * HOUR + 15 * 60_000), due_has_time: true }),
  base({ todo_id: "stub-t3", title: "Chase the fee note", matter_id: 9003, client_name: "Third Stubperson", due_utc: endOfDay(today()) }),
];

const CATEGORY_KEYS = ["court", "bundle", "signing", "statements", "drafts", "caseflow"];
let autoOn = true;
let autoHidden: string[] = [];
const automatic: { cat: string; todo: Todo }[] = [
  { cat: "court", todo: base({ todo_id: "stub-a1", title: "Chase the court: no reply to the without-notice application", matter_id: 9001, client_name: "Stub Testperson", source: "nudge", due_utc: endOfDay(today()) }) },
  { cat: "caseflow", todo: base({ todo_id: "stub-a3", title: "Auto mode could not do the court pack step", matter_id: 9001, client_name: "Stub Testperson", source: "auto-blocked" }) },
  { cat: "bundle", todo: base({ todo_id: "stub-a2", title: "Print and post the final hearing bundle", matter_id: 9003, client_name: "Third Stubperson", source: "nudge" }) },
];
const shownAuto = (cat?: string): Todo[] =>
  autoOn ? automatic.filter((a) => !autoHidden.includes(a.cat) && (!cat || a.cat === cat) && !a.todo.done_utc).map((a) => decorate(a.todo)) : [];

export function stubSetAutomatic(show: boolean, hidden: string[]): TodoSummary {
  autoOn = show;
  autoHidden = hidden.filter((k) => CATEGORY_KEYS.includes(k));
  return stubSummary();
}

function decorate(t: Todo): Todo {
  const isoNow = iso(Date.now());
  return {
    ...t,
    is_done: !!t.done_utc,
    is_overdue: !!t.due_utc && !t.done_utc && t.due_utc < isoNow,
    on_my_day_today: t.my_day_date === today(),
  };
}

export function stubListTodos(q: { view: string; matterId: number | null; includeDone: boolean }): Todo[] {
  if (q.view.startsWith("auto_")) return shownAuto(q.view.slice(5));
  let rows = todos.filter((t) => !t.deleted).map(decorate);

  if (q.view === "completed") rows = rows.filter((t) => t.is_done);
  else if (q.view === "tasks" || !q.includeDone) rows = rows.filter((t) => !t.is_done);
  if (q.matterId != null) rows = rows.filter((t) => t.matter_id === q.matterId);
  if (q.view === "my_day") rows = rows.filter((t) => t.on_my_day_today);
  if (q.view === "important") rows = rows.filter((t) => t.starred);
  if (q.view === "planned") rows = rows.filter((t) => t.due_utc);
  if (q.view === "completed") return rows.sort((a, b) => (b.done_utc ?? "").localeCompare(a.done_utc ?? ""));
  if (q.view === "all" && q.matterId == null) rows = [...rows, ...shownAuto()];
  return rows.sort((a, b) => Number(a.is_done) - Number(b.is_done) || (a.due_utc ? 0 : 1) - (b.due_utc ? 0 : 1) || (a.due_utc ?? "").localeCompare(b.due_utc ?? ""));
}

export function stubSummary(): TodoSummary {
  const open = todos.filter((t) => !t.deleted && !t.done_utc).map(decorate);
  const completedCount = todos.filter((t) => !t.deleted && t.done_utc).length;
  const endToday = endOfDay(today());
  const overdue = open.filter((t) => t.is_overdue).length;
  const dueToday = open.filter((t) => t.due_utc && !t.is_overdue && t.due_utc <= endToday).length;
  const counts: TodoSummary = {
    open: open.length,
    tasks: open.length,
    completed: completedCount,
    all: open.length + completedCount + shownAuto().length,
    overdue,
    important: open.filter((t) => t.starred).length,
    planned: open.filter((t) => t.due_utc).length,
    my_day: open.filter((t) => t.on_my_day_today).length,
    attention: overdue + dueToday,
    auto_on: autoOn ? 1 : 0,
  };
  for (const key of CATEGORY_KEYS) {
    counts[`hide_${key}`] = autoHidden.includes(key) ? 1 : 0;
    counts[`cat_${key}`] = shownAuto(key).length;
  }
  return counts;
}

export function stubCreateTodo(b: Record<string, unknown>): Todo | { error: string } {
  const title = String(b.title ?? "").trim();
  if (!title) return { error: "a task needs a title" };
  const dueRaw = b.due ? String(b.due) : "";
  const due = !dueRaw ? null : /^\d{4}-\d{2}-\d{2}$/.test(dueRaw) ? endOfDay(dueRaw) : iso(new Date(dueRaw).getTime());
  seq += 1;
  const todo = base({
    todo_id: `stub-t${seq}`, title, matter_id: b.matter_id ? Number(b.matter_id) : null,
    client_name: b.matter_id ? (Number(b.matter_id) === 9001 ? "Stub Testperson" : Number(b.matter_id) === 9002 ? "Second Stubperson" : "Third Stubperson") : null,
    created_by: String(b.created_by ?? ""),
    due_utc: due, due_has_time: !!b.due_has_time && !!due, starred: !!b.starred, my_day_date: b.my_day ? today() : null,
  });
  todos.push(todo);
  return decorate(todo);
}

export function stubUpdateTodo(id: string, fields: Record<string, unknown>): Todo | { error: string } {
  const t = todos.find((x) => x.todo_id === id && !x.deleted);
  if (!t) return { error: `no such task: ${id}` };
  if ("title" in fields) t.title = String(fields.title).trim() || t.title;
  if ("starred" in fields) t.starred = !!fields.starred;
  if ("my_day" in fields) t.my_day_date = fields.my_day ? today() : null;
  if ("due_utc" in fields) {
    const v = fields.due_utc ? String(fields.due_utc) : "";
    t.due_utc = !v ? null : /^\d{4}-\d{2}-\d{2}$/.test(v) ? endOfDay(v) : iso(new Date(v).getTime());
    t.due_has_time = !!v && !/^\d{4}-\d{2}-\d{2}$/.test(v);
  }
  t.updated_utc = iso(Date.now());
  return decorate(t);
}

export function stubCompleteTodo(id: string, done: boolean, by: string): Todo | { error: string } {
  const t = todos.find((x) => x.todo_id === id && !x.deleted);
  if (!t) return { error: `no such task: ${id}` };
  t.done_utc = done ? iso(Date.now()) : null;
  t.done_by = done ? by : "";
  return decorate(t);
}

export function stubDeleteTodo(id: string): { ok: true } | { error: string } {
  const t = todos.find((x) => x.todo_id === id);
  if (!t) return { error: `no such task: ${id}` };
  t.deleted = true;
  return { ok: true };
}

export function stubEmailClientTodo(id: string): { todo: Todo; draft_link: string; warning: string; created: boolean } | { error: string } {
  const t = todos.find((x) => x.todo_id === id && !x.deleted);
  if (!t) return { error: `no such task: ${id}` };
  if (t.matter_id == null) return { error: "this task is not tied to a client" };
  const created = !t.draft_link;
  if (created) t.draft_link = `https://outlook.office.com/mail/drafts/stub-${id}`;
  t.updated_utc = iso(Date.now());
  return { todo: decorate(t), draft_link: t.draft_link as string, warning: "", created };
}
