"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { backgroundFetch } from "./loadingBar";

export const AUTO_CATEGORIES = [
  { key: "court", label: "Court" },
  { key: "bundle", label: "Bundle" },
  { key: "signing", label: "Signing" },
  { key: "statements", label: "Statements" },
  { key: "drafts", label: "Drafts" },
  { key: "caseflow", label: "Case flow" },
] as const;
export type AutoKey = (typeof AUTO_CATEGORIES)[number]["key"];
export type PersonalView = "my_day" | "important" | "planned" | "tasks" | "completed" | "all";
export type TodoView = PersonalView | `auto_${AutoKey}`;

export interface Todo {
  todo_id: string;
  title: string;
  notes: string;
  matter_id: number | null;
  client_name: string | null;
  created_by: string;
  due_utc: string | null;
  due_has_time: boolean;
  starred: boolean;
  my_day_date: string | null;
  on_my_day_today: boolean;
  is_done: boolean;
  is_overdue: boolean;
  source: string;
  created_utc: string;
  updated_utc: string;
  done_utc: string | null;
  done_by: string;

  draft_link?: string;
}

export type TodoSummary = Record<string, number>;

export interface TodoQuery {
  view: TodoView;
  matterId?: number | null;
  includeDone?: boolean;
}

export function viewLabel(view: TodoView): string {
  if (view.startsWith("auto_")) return AUTO_CATEGORIES.find((c) => `auto_${c.key}` === view)?.label ?? "Automatic";
  return VIEW_LABELS[view as PersonalView];
}

export const TODOS_CHANGED_EVENT = "caseforge:todos-changed";

export function notifyTodosChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(TODOS_CHANGED_EVENT));
}

export const VIEW_LABELS: Record<PersonalView, string> = {
  my_day: "My Day",
  important: "Important",
  planned: "Planned",
  tasks: "Tasks",
  completed: "Completed",
  all: "All",
};

function queryString(q: TodoQuery): string {
  const params = new URLSearchParams({ view: q.view });
  if (q.matterId != null) params.set("matter_id", String(q.matterId));

  if (q.includeDone || q.view === "all") params.set("include_done", "true");
  return params.toString();
}

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchTodos(q: TodoQuery, background = false): Promise<{ items: Todo[]; summary: TodoSummary }> {
  const url = `/api/todos?${queryString(q)}`;
  const res = background ? await backgroundFetch(url, { cache: "no-store" }) : await fetch(url, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load tasks.");
  const body = await res.json();
  return { items: body.items ?? [], summary: body.summary ?? {} };
}

export async function fetchTodoSummary(): Promise<TodoSummary> {
  const res = await backgroundFetch("/api/todos/summary", { cache: "no-store" });
  if (!res.ok) return {};
  return (await res.json()).summary ?? {};
}

async function post(path: string, body: unknown, fallback: string): Promise<Response> {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) await readError(res, fallback);
  return res;
}

export interface NewTodo {
  title: string;
  matterId?: number | null;
  due?: string | null;
  dueHasTime?: boolean;
  starred?: boolean;
  myDay?: boolean;
}

export async function createTodo(t: NewTodo): Promise<Todo> {
  const res = await post(
    "/api/todos",
    {
      title: t.title,
      matter_id: t.matterId ?? null,
      due: t.due ?? null,
      due_has_time: t.dueHasTime ?? false,
      starred: t.starred ?? false,
      my_day: t.myDay ?? false,
    },
    "Could not add the task.",
  );
  notifyTodosChanged();
  return res.json();
}

export async function updateTodo(todoId: string, fields: Record<string, unknown>): Promise<Todo> {
  const res = await post("/api/todos/update", { todo_id: todoId, fields }, "Could not change the task.");
  notifyTodosChanged();
  return res.json();
}

export async function completeTodo(todoId: string, done: boolean): Promise<Todo> {
  const res = await post("/api/todos/complete", { todo_id: todoId, done }, "Could not update the task.");
  notifyTodosChanged();
  return res.json();
}

export async function deleteTodo(todoId: string): Promise<void> {
  await post("/api/todos/delete", { todo_id: todoId }, "Could not remove the task.");
  notifyTodosChanged();
}

export async function setAutomatic(show: boolean, hidden: string[]): Promise<TodoSummary> {
  const res = await post("/api/todos/automatic", { show, hidden }, "Could not change that.");
  notifyTodosChanged();
  return (await res.json()).summary ?? {};
}

export interface EmailClientResult {
  todo: Todo;
  draft_link: string;

  warning: string;
  created: boolean;
}

export async function emailClientTodo(todoId: string): Promise<EmailClientResult> {
  const res = await post("/api/todos/email-client", { todo_id: todoId }, "Could not make the draft.");
  notifyTodosChanged();
  return res.json();
}

export function useTodos(query: TodoQuery): {
  items: Todo[];
  summary: TodoSummary;
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [state, setState] = useState<{ items: Todo[]; summary: TodoSummary; loading: boolean; error: string | null }>({
    items: [],
    summary: {},
    loading: true,
    error: null,
  });
  const key = queryString(query);
  const queryRef = useRef(query);
  queryRef.current = query;
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const silentRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const silent = silentRef.current;
    silentRef.current = false;
    if (!silent) setState((s) => ({ ...s, loading: true }));
    fetchTodos(queryRef.current, silent)
      .then((r) => !cancelled && setState({ items: r.items, summary: r.summary, loading: false, error: null }))
      .catch((err: unknown) => {
        if (!cancelled) setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : "Could not load tasks." }));
      });
    return () => {
      cancelled = true;
    };
  }, [key, nonce]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      silentRef.current = true;
      refresh();
    }, 120_000);
    window.addEventListener(TODOS_CHANGED_EVENT, refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(TODOS_CHANGED_EVENT, refresh);
    };
  }, [refresh]);

  return { ...state, refresh };
}

export function useMinuteClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}
