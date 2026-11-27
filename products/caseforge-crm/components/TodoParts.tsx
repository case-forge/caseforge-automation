"use client";

import { IconCheck, IconEnvelope, IconExternalLink, IconPencil, IconStar, IconSun, IconTrash } from "./icons";
import { SortMenu } from "./TodoToolbar";
import { ClearableSearch } from "./ClearableSearch";
import type { TodoSort } from "@/lib/todoSort";
import { useEffect, useState } from "react";
import { useCurrentClient, useReportUnsaved } from "@/lib/unsavedEdits";
import { useFormDraft } from "@/lib/formDrafts";
import { DraftRestoredNote } from "./DraftRestoredNote";
import { countdown, countdownText } from "@/lib/todoCountdown";
import { offerableDue, parseTodoText } from "@/lib/todoDates";
import { completeTodo, createTodo, deleteTodo, emailClientTodo, updateTodo } from "@/lib/todos";
import { safeLink } from "@/lib/todayBoard";
import type { Todo } from "@/lib/todos";

function dueLabel(due: string, hasTime: boolean, now: Date): { text: string; overdue: boolean; title: string } | null {
  const c = countdown(due, now);
  if (!c) return null;
  const when = new Date(due).toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(hasTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: "Europe/London",
  });
  return { text: countdownText(c), overdue: c.overdue, title: `${when} (${c.long})` };
}

export function TodoAddBox({
  matterId,
  defaultMyDay = false,
  defaultStarred = false,
  now,
  search,
  onSearch,
  sort,
  onSort,
  canAdd = true,
}: {
  matterId?: number | null;
  defaultMyDay?: boolean;
  defaultStarred?: boolean;
  now: Date;

  onSearch: (s: string) => void;
  sort: TodoSort;
  onSort: (s: TodoSort) => void;
  search?: string;

  canAdd?: boolean;
}) {
  const [text, setTextState] = useState(search ?? "");
  const setText = (value: string) => {
    setTextState(value);
    onSearch(value);
  };
  const [starred, setStarred] = useState(defaultStarred);
  const [myDay, setMyDay] = useState(defaultMyDay);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [acceptedKey, setAcceptedKey] = useState("");
  const [dismissedKeys, setDismissedKeys] = useState<string[]>([]);

  const sourceId = matterId != null ? `todo-add-${matterId}` : "todo-add";
  const client = useCurrentClient();
  const onPanel = !!client && matterId != null && client.matterId === String(matterId);
  const dirty = text.trim() !== "";
  useReportUnsaved(
    sourceId,
    {
      label: "New to-do",
      matterId: matterId != null ? String(matterId) : undefined,
      clientName: onPanel ? client.clientName : undefined,
      place: onPanel ? client.tab : "To-do list",
    },
    dirty,
  );

  const kept = useFormDraft<{ text: string }>({
    matterId,
    formId: "todo-add",
    dirty: dirty && canAdd,
    data: { text },
    restore: (saved) => {
      if (typeof saved.text !== "string" || !saved.text.trim()) return false;
      setText(saved.text);
    },
  });

  useEffect(() => setMyDay(defaultMyDay), [defaultMyDay]);
  useEffect(() => setStarred(defaultStarred), [defaultStarred]);

  const parsed = parseTodoText(text, now);

  const offer = offerableDue(parsed, now);
  const offerKey = offer ? `${offer.due}|${offer.matchedText}` : "";
  const accepted = !!offer && acceptedKey === offerKey;
  const dismissed = !!offer && dismissedKeys.includes(offerKey);
  const preview = offer ? dueLabel(offer.due!.length === 10 ? new Date(`${offer.due}T23:59:00`).toISOString() : offer.due!, offer.hasTime, now) : null;

  const printButton = (
    <button type="button" className="cf-btn cf-btn--neutral todo-act" onClick={() => window.print()}>
      Print
    </button>
  );
  const title = accepted ? parsed.title : text.trim().replace(/\s+/g, " ");
  const due = accepted ? offer!.due : null;
  const dueHasTime = accepted ? offer!.hasTime : false;

  async function add() {
    if (!canAdd || busy || !title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createTodo({
        title,
        matterId: matterId ?? null,
        due,
        dueHasTime,
        starred,
        myDay,
      });
      setText("");
      setAcceptedKey("");
      setStarred(defaultStarred);
      setMyDay(defaultMyDay);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the task.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="todo-add todo-compose"
      data-unsaved-source={sourceId}
      onSubmit={(e) => {
        e.preventDefault();
        void add();
      }}
    >
      <div className="todo-compose-bar">
        <div className="todo-compose-field">
        <ClearableSearch
          wrapClassName="todo-compose-search"
          className="todo-add-input"
          value={text}
          onValueChange={setText}
          clearLabel="Clear the search"
          placeholder={canAdd ? "Search, or type a task and press Enter" : "Search tasks"}
          aria-label={canAdd ? "Search tasks or add a new one" : "Search tasks"}
          maxLength={300}
        />
        </div>
      </div>
      { }
      <div className="todo-add-row">
        {canAdd && (
          <>
            <button type="button" className="cf-btn cf-btn--chip todo-act" aria-pressed={starred} onClick={() => setStarred(!starred)}>
              <IconStar filled={starred} aria-hidden="true" /> Important
            </button>
            <button type="button" className="cf-btn cf-btn--chip todo-act" aria-pressed={myDay} onClick={() => setMyDay(!myDay)}>
              <IconSun filled={myDay} aria-hidden="true" /> {myDay ? "In My Day" : "My Day"}
            </button>
          </>
        )}
        <SortMenu sort={sort} onSort={onSort} />
        {canAdd && (
          <button type="submit" className="cf-btn cf-btn--primary todo-act">
            Add
          </button>
        )}
        {printButton}
      </div>
      {offer && preview && !accepted && !dismissed && (
        <p className="todo-date-offer" role="status">
          <span>
            Set the due date to <strong>{preview.title}</strong>?
          </span>
          <button type="button" className="cf-btn cf-btn--secondary cf-btn--small" onClick={() => setAcceptedKey(offerKey)}>
            Set due date
          </button>
          <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => setDismissedKeys((keys) => [...keys, offerKey])}>
            Dismiss
          </button>
        </p>
      )}
      {accepted && preview && (
        <p className="todo-add-preview" data-overdue={preview.overdue} title={preview.title}>
          Due {preview.title}
          <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => setAcceptedKey("")}>
            Remove due date
          </button>
        </p>
      )}
      <DraftRestoredNote savedAt={kept.restoredAt} saveLabel="Add" onDiscard={() => setText("")} />
      {error && (
        <p className="todo-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

export function TodoRow({
  todo,
  now,
  showClient,
  onOpenClient,
}: {
  todo: Todo;
  now: Date;
  showClient: boolean;
  onOpenClient?: (clientName: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(todo.title);

  const automatic = todo.source !== "manual";
  const due = todo.due_utc ? dueLabel(todo.due_utc, todo.due_has_time, now) : null;

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not save.");
    }
  }

  function startEdit() {
    if (automatic) return;
    setDraft(todo.title);
    setEditing(true);
  }

  async function saveEdit() {
    const title = draft.replace(/\s+/g, " ").trim();
    setEditing(false);
    if (!title || title === todo.title) return;
    await run(() => updateTodo(todo.todo_id, { title }));
  }

  return (
    <li className="todo-row" data-done={todo.is_done}>
      <span className="todo-check-wrap">
        <input
          type="checkbox"
          className="todo-check"
          checked={todo.is_done}
          aria-label={todo.is_done ? `Reopen: ${todo.title}` : `Done: ${todo.title}`}
          onChange={() => void run(() => completeTodo(todo.todo_id, !todo.is_done))}
        />
        <IconCheck aria-hidden="true" />
      </span>
      <div className="todo-body">
        {editing ? (
          <input
            className="todo-title-edit"
            value={draft}
            autoFocus
            aria-label={`Edit task: ${todo.title}`}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => void saveEdit()}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void saveEdit();
              } else if (e.key === "Escape") {
                setEditing(false);
              }
            }}
          />
        ) : (
          <span className="todo-title" onDoubleClick={startEdit}>
            {todo.title}
          </span>
        )}
        <span className="todo-meta">
          {due && !todo.is_done && (
            <span className="todo-due" data-overdue={due.overdue} title={due.title}>
              {due.text}
            </span>
          )}
          {showClient && todo.client_name && (
            <button type="button" className="cf-btn cf-btn--link todo-client" onClick={() => onOpenClient?.(todo.client_name as string)}>
              {todo.client_name}
            </button>
          )}
        </span>
        {error && (
          <span className="todo-error" role="alert">
            {error}
          </span>
        )}
      </div>
      {!automatic && (
      <div className="todo-actions">
        <button
          type="button"
          className="cf-btn cf-btn--icon"
          aria-pressed={todo.starred}
          aria-label={todo.starred ? "Not important" : "Important"}
          title="Important"
          onClick={() => void run(() => updateTodo(todo.todo_id, { starred: !todo.starred }))}
        >
          <IconStar filled={todo.starred} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="cf-btn cf-btn--icon"
          aria-pressed={todo.on_my_day_today}
          aria-label={todo.on_my_day_today ? "Remove from My Day" : "Add to My Day"}
          title="My Day"
          onClick={() => void run(() => updateTodo(todo.todo_id, { my_day: !todo.on_my_day_today }))}
        >
          <IconSun filled={todo.on_my_day_today} aria-hidden="true" />
        </button>
        {todo.matter_id != null && todo.draft_link && safeLink(todo.draft_link) ? (
          <a
            className="cf-btn cf-btn--icon"
            href={safeLink(todo.draft_link) as string}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open draft: ${todo.title}`}
            title="Open draft"
          >
            <IconExternalLink aria-hidden="true" />
          </a>
        ) : (
          todo.matter_id != null && (
            <button
              type="button"
              className="cf-btn cf-btn--icon"
              aria-label={`Email client: ${todo.title}`}
              title="Email client"
              onClick={() => void run(async () => {
                const made = await emailClientTodo(todo.todo_id);
                if (made.warning) setError(`Draft made. Check before sending: ${made.warning}`);
              })}
            >
              <IconEnvelope aria-hidden="true" />
            </button>
          )
        )}
        <button
          type="button"
          className="cf-btn cf-btn--icon"
          aria-label={`Edit: ${todo.title}`}
          title="Edit"
          aria-pressed={editing}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => (editing ? void saveEdit() : startEdit())}
        >
          <IconPencil aria-hidden="true" />
        </button>
        <button
          type="button"
          className="cf-btn cf-btn--icon cf-btn--danger"
          aria-label={`Delete: ${todo.title}`}
          title="Delete"
          onClick={() => void run(() => deleteTodo(todo.todo_id))}
        >
          <IconTrash aria-hidden="true" />
        </button>
      </div>
      )}
    </li>
  );
}
