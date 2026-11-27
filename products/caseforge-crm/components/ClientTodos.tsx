"use client";

import { useMinuteClock, useTodos } from "@/lib/todos";
import { filterAndSort } from "@/lib/todoSort";
import { TodoAddBox, TodoRow } from "./TodoParts";
import { useTodoToolbar } from "./TodoToolbar";

export function ClientTodos({ matterId }: { matterId: number }) {
  const now = useMinuteClock();
  const { items: all, loading, error } = useTodos({ view: "all", matterId });
  const { search, setSearch, sort, setSort } = useTodoToolbar();
  const items = filterAndSort(all, search, sort);

  return (
    <div className="todo-tab">
      <TodoAddBox matterId={matterId} now={now} search={search} onSearch={setSearch} sort={sort} onSort={setSort} />
      {error && (
        <p className="todo-error" role="alert">
          {error}
        </p>
      )}
      {loading && all.length === 0 ? (
        <p className="todo-empty">Loading tasks...</p>
      ) : items.length === 0 ? (
        <p className="todo-empty">{all.length > 0 ? "No tasks match your search." : "No open tasks for this client."}</p>
      ) : (
        <div className="todo-print-area">
          <h2 className="todo-print-title">Tasks</h2>
          <ul className="todo-list">
            {items.map((t) => (
              <TodoRow key={t.todo_id} todo={t} now={now} showClient={false} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
