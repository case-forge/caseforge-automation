"use client";

import { useEffect, useRef, useState } from "react";
import { useDismiss } from "@/lib/dismiss";
import { HeaderOverflowEntry } from "./HeaderOverflow";
import type { SVGProps } from "react";
import { AUTO_CATEGORIES, VIEW_LABELS, fetchTodoSummary, setAutomatic, useMinuteClock, useTodos, viewLabel, TODOS_CHANGED_EVENT } from "@/lib/todos";
import type { PersonalView, TodoSummary, TodoView } from "@/lib/todos";
import { filterAndSort } from "@/lib/todoSort";
import { TodoAddBox, TodoRow } from "./TodoParts";
import { useTodoToolbar } from "./TodoToolbar";
import { IconEye, IconEyeOff } from "./icons";
import { startVisiblePoll } from "@/lib/visiblePoll";

export function IconTick(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4.5 12.5l4.8 4.8L19.5 7" />
    </svg>
  );
}

const FIXED: PersonalView[] = ["my_day", "important", "planned", "tasks", "completed", "all"];

export function badgeLabel(attention: number): string {
  return attention > 0 ? `Tasks, ${attention} need attention` : "Tasks";
}

function useSummary(): TodoSummary {
  const [summary, setSummary] = useState<TodoSummary>({});
  useEffect(() => {
    let cancelled = false;
    const load = () => void fetchTodoSummary().then((s) => !cancelled && setSummary(s)).catch(() => {});
    const stopPoll = startVisiblePoll(load, 120_000);
    window.addEventListener(TODOS_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      stopPoll();
      window.removeEventListener(TODOS_CHANGED_EVENT, load);
    };
  }, []);
  return summary;
}

export function TodoHeader({ onOpenClient }: { onOpenClient?: (name: string) => void }) {
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState<TodoView>("my_day");
  const rootRef = useRef<HTMLDivElement>(null);
  const summary = useSummary();
  const attention = summary.attention ?? 0;

  const entryRef = useRef<HTMLButtonElement>(null);
  useDismiss(open, () => setOpen(false), rootRef, entryRef);

  return (
    <div className="attention" ref={rootRef}>
      <button
        type="button"
        className="cf-btn cf-btn--flush attention-button attention-button--todo"
        data-header-measure=""
        data-active={attention > 0}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={badgeLabel(attention)}
        title="Tasks"
        onClick={() => setOpen((v) => !v)}
      >
        <IconTick />
        {attention > 0 && (
          <span className="attention-count" aria-hidden="true">
            {attention}
          </span>
        )}
      </button>
      <HeaderOverflowEntry
        ref={entryRef}
        icon={<IconTick />}
        label="Tasks"
        ariaLabel={badgeLabel(attention)}
        count={attention}
        tone="attention-button--todo"
        active={attention > 0}
        expanded={open}
        onClick={() => setOpen((v) => !v)}
      />
      {open && (
        <TodoPanel
          sel={sel}
          onSel={setSel}
          summary={summary}
          onOpenClient={
            onOpenClient
              ? (n) => {
                  setOpen(false);
                  onOpenClient(n);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}

function TodoPanel({
  sel,
  onSel,
  summary,
  onOpenClient,
}: {
  sel: TodoView;
  onSel: (s: TodoView) => void;
  summary: TodoSummary;
  onOpenClient?: (n: string) => void;
}) {
  const now = useMinuteClock();
  const { items: all, loading, error } = useTodos({ view: sel });
  const { search, setSearch, sort, setSort } = useTodoToolbar();
  const items = filterAndSort(all, search, sort);
  const title = viewLabel(sel);
  const automaticOn = (summary.auto_on ?? 1) === 1;
  const hiddenKeys = AUTO_CATEGORIES.filter((c) => summary[`hide_${c.key}`] === 1).map((c) => c.key as string);
  const [switchError, setSwitchError] = useState<string | null>(null);

  const change = (show: boolean, hidden: string[]) => {
    setSwitchError(null);
    setAutomatic(show, hidden).catch((err: unknown) => setSwitchError(err instanceof Error ? err.message : "Could not change that."));
  };

  const canAdd = sel !== "completed" && !sel.startsWith("auto_");

  return (
    <div className="attention-panel todo-panel" role="dialog" aria-label="Tasks">
      <nav className="todo-side" aria-label="Task lists">
        {FIXED.map((v) => (
          <button key={v} type="button" className="cf-btn cf-btn--flush cf-btn--row todo-side-item" data-active={v === sel} onClick={() => onSel(v)}>
            <span>{VIEW_LABELS[v]}</span>
            <span className="todo-side-count">{summary[v] ?? 0}</span>
          </button>
        ))}
        <label className="todo-side-heading todo-auto-switch" title="Shows the automatic chase tasks to everyone in the firm">
          <input type="checkbox" checked={automaticOn} onChange={(e) => change(e.target.checked, hiddenKeys)} />
          <span>Show automatic</span>
        </label>
        {automaticOn &&
          AUTO_CATEGORIES.map((c) => {
            const view = `auto_${c.key}` as TodoView;
            const hidden = hiddenKeys.includes(c.key);
            return (
              <span key={c.key} className="todo-side-row" data-hidden={hidden}>
                <button
                  type="button"
                  className="cf-btn cf-btn--flush cf-btn--row todo-side-item"
                  data-active={view === sel}
                  disabled={hidden}
                  onClick={() => onSel(view)}
                >
                  <span>{c.label}</span>
                  <span className="todo-side-count">{hidden ? "" : (summary[`cat_${c.key}`] ?? 0)}</span>
                </button>
                <button
                  type="button"
                  className="cf-btn cf-btn--icon cf-btn--compact todo-side-eye"
                  aria-label={hidden ? `Show ${c.label} for everyone` : `Hide ${c.label} for everyone`}
                  title={hidden ? `Show ${c.label} for everyone` : `Hide ${c.label} for everyone`}
                  onClick={() => change(true, hidden ? hiddenKeys.filter((k) => k !== c.key) : [...hiddenKeys, c.key])}
                >
                  {hidden ? <IconEyeOff aria-hidden="true" /> : <IconEye aria-hidden="true" />}
                </button>
              </span>
            );
          })}
      </nav>
      <div className="todo-main">
        <h2 className="attention-panel-title">{title}</h2>
        <TodoAddBox
          now={now}
          canAdd={canAdd}
          search={search}
          onSearch={setSearch}
          sort={sort}
          onSort={setSort}
          defaultMyDay={sel === "my_day"}
          defaultStarred={sel === "important"}
        />
        {(error || switchError) && (
          <p className="todo-error" role="alert">
            {error || switchError}
          </p>
        )}
        {sel.startsWith("auto_") && hiddenKeys.includes(sel.slice(5)) ? (
          <p className="todo-empty">This list is switched off for everyone.</p>
        ) : loading && all.length === 0 ? (
          <p className="todo-empty">Loading tasks...</p>
        ) : items.length === 0 ? (
          <p className="todo-empty">
            {all.length > 0 ? "No tasks match your search." : sel === "completed" ? "Nothing has been completed yet." : "Nothing here."}
          </p>
        ) : (
          <div className="todo-print-area">
            <h2 className="todo-print-title">{title}</h2>
            <ul className="todo-list">
              {items.map((t) => (
                <TodoRow key={t.todo_id} todo={t} now={now} showClient onOpenClient={onOpenClient} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
