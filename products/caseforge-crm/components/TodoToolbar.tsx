"use client";

import { useEffect, useRef, useState } from "react";
import { useDismiss } from "@/lib/dismiss";
import { SORT_LABELS } from "@/lib/todoSort";
import type { TodoSort } from "@/lib/todoSort";
import { IconCheck, IconSortAZ } from "./icons";

const SORT_ORDER: TodoSort[] = ["due_soonest", "due_latest", "important", "newest", "oldest", "az", "za"];

export function useTodoToolbar(): { search: string; setSearch: (s: string) => void; sort: TodoSort; setSort: (s: TodoSort) => void } {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<TodoSort>("due_soonest");
  return { search, setSearch, sort, setSort };
}

export function SortMenu({ sort, onSort }: { sort: TodoSort; onSort: (s: TodoSort) => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useDismiss(open, () => setOpen(false), rootRef, buttonRef);

  useEffect(() => {
    if (!open) return;
    const items = menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]');
    (items && (Array.from(items).find((el) => el.getAttribute("aria-checked") === "true") ?? items[0]))?.focus();
  }, [open]);
  function onMenuKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") items[(at + 1) % items.length]?.focus();
    else if (e.key === "ArrowUp") items[(at - 1 + items.length) % items.length]?.focus();
    else if (e.key === "Home") items[0]?.focus();
    else if (e.key === "End") items[items.length - 1]?.focus();
    else if (e.key === "Escape") {

      e.stopPropagation();
      e.nativeEvent.stopImmediatePropagation();
      setOpen(false);
      buttonRef.current?.focus();
      return;
    } else if (e.key === "Tab") {
      setOpen(false);
      return;
    } else return;
    e.preventDefault();
  }
  return (
    <span className="todo-sort-wrap" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="cf-btn cf-btn--chip todo-act todo-sort-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Sort tasks: ${SORT_LABELS[sort]}`}
        title={`Sort: ${SORT_LABELS[sort]}`}
        onClick={() => setOpen((v) => !v)}
      >
        <IconSortAZ aria-hidden="true" />
      </button>
      {open && (
        <div className="todo-sort-menu" role="menu" aria-label="Sort tasks" ref={menuRef} onKeyDown={onMenuKey}>
          {SORT_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              role="menuitemradio"
              aria-checked={s === sort}
              className="cf-btn cf-btn--flush cf-btn--row todo-sort-item"
              onClick={() => {
                onSort(s);
                setOpen(false);
              }}
            >
              <span>{SORT_LABELS[s]}</span>
              {s === sort && <IconCheck aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
