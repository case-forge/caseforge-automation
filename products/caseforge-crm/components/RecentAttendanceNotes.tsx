"use client";

import { startVisiblePoll } from "@/lib/visiblePoll";
import { useCallback, useEffect, useRef, useState } from "react";
import { loadSent } from "@/lib/anDrafts";
import type { AttendanceNoteStatus } from "@/lib/types";
import { ATTENDANCE_KIND_LABELS, filedLabel, isAttendanceKind } from "@/lib/types";

export interface TakenBackNote {
  draftId: string;
  caller: string;
  callerOther: string;
  noteText: string;
  timeMinutes: number | null;

  kind?: string;
}
import { RemoveBillingButton } from "./RemoveBillingButton";
import { backgroundFetch } from "@/lib/loadingBar";

const POLL_MS = 3000;

function whenLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function RecentAttendanceNotes({
  matterId,
  refreshSignal,
  onFiled,
  onEdit,
  onNoteFiled,
}: {
  matterId: string;

  refreshSignal: number;

  onFiled: () => void;

  onEdit?: (note: TakenBackNote) => void;

  onNoteFiled?: (draftId: string) => void;
}) {
  const [items, setItems] = useState<AttendanceNoteStatus[]>([]);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editError, setEditError] = useState<{ id: string; message: string } | null>(null);
  const onNoteFiledRef = useRef(onNoteFiled);
  onNoteFiledRef.current = onNoteFiled;
  const seenFiling = useRef<Set<string>>(new Set());
  const onFiledRef = useRef(onFiled);
  onFiledRef.current = onFiled;

  const load = useCallback(async (silent = false) => {
    try {
      const url = `/api/attendance-notes/recent?matter_id=${encodeURIComponent(matterId)}`;
      const res = silent ? await backgroundFetch(url) : await fetch(url);
      if (!res.ok) return;
      const body = (await res.json()) as { items?: AttendanceNoteStatus[] };
      const next = body.items ?? [];
      for (const item of next) {
        if (item.state === "filing") seenFiling.current.add(item.draft_id);
        else if (item.state === "filed") {
          onNoteFiledRef.current?.(item.draft_id);
          if (seenFiling.current.delete(item.draft_id)) onFiledRef.current();
        }
      }
      setItems(next);
    } catch {

    }
  }, [matterId]);

  useEffect(() => {
    seenFiling.current = new Set();
    void load();
  }, [load, refreshSignal]);

  const anyFiling = items.some((i) => i.state === "filing");
  useEffect(() => {
    if (!anyFiling) return;
    return startVisiblePoll(() => void load(true), POLL_MS, { immediate: false });
  }, [anyFiling, load]);

  async function retry(draftId: string) {
    setRetrying(draftId);
    try {
      await fetch("/api/attendance-notes/retry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_id: draftId }),
      });
    } finally {
      setRetrying(null);
      void load();
    }
  }

  async function edit(draftId: string) {
    if (!onEdit) return;
    setEditing(draftId);
    setEditError(null);
    try {
      let taken: TakenBackNote | null = null;
      try {
        const res = await fetch("/api/attendance-notes/edit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ draft_id: draftId }),
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok) {
          taken = {
            draftId,
            caller: String(body.caller ?? ""),
            callerOther: String(body.caller_other ?? ""),
            noteText: String(body.note_text ?? ""),
            timeMinutes: typeof body.time_minutes === "number" ? body.time_minutes : null,
            kind: typeof body.kind === "string" ? body.kind : "call",
          };
        } else if (res.status < 500) {
          setEditError({ id: draftId, message: body.error || "Could not open the note to edit." });
          return;
        }
      } catch {

      }
      if (!taken) {
        const local = loadSent(matterId).find((n) => n.draftId === draftId);
        if (!local) {
          setEditError({ id: draftId, message: "Could not reach the server, and this browser has no copy of that note." });
          return;
        }
        taken = { draftId, caller: local.caller, callerOther: local.callerOther, noteText: local.noteText, timeMinutes: null };
      }
      onEdit(taken);
    } finally {
      setEditing(null);
      void load();
    }
  }

  if (items.length === 0) return null;

  return (
    <ul className="an-recent no-print" aria-label="Recent attendance notes">
      {[...items].sort((a, b) => Number(b.state === "failed" || !!b.unsorted) - Number(a.state === "failed" || !!a.unsorted)).slice(0, 8).map((item) => (
        <li key={item.draft_id} className="an-recent-item" data-state={item.state}>
          <span className="an-recent-when">{whenLabel(item.created_utc)}</span>
          {isAttendanceKind(item.kind) && item.kind !== "call" && (
            <span className="an-recent-when"> {ATTENDANCE_KIND_LABELS[item.kind]}</span>
          )}
          {item.state === "filing" && (
            <span className="an-recent-state" role="status">
              {item.error
                ? `Trying again: ${item.error}`
                : "Filing in background. Safe to close."}
            </span>
          )}
          {item.state === "filed" && (
            <span className="an-recent-state">
              {filedLabel(item)}{" "}
              {item.an_url && (
                <a href={item.an_url} target="_blank" rel="noreferrer">
                  Open the note
                </a>
              )}{" "}
              {item.filed_folder && <small>In {item.filed_folder}. </small>}
              {!item.billing_removed && item.billing_item_id && (
                <RemoveBillingButton draftId={item.draft_id} onRemoved={() => { void load(); onFiledRef.current(); }} />
              )}
            </span>
          )}
          {item.state === "filed" && item.billing_note && (
            <span className="an-recent-state an-recent-state--failed" role="alert">
              {item.billing_note}
            </span>
          )}
          {item.state === "filed" && item.unsorted && (
            <span className="an-recent-state an-recent-state--failed" role="alert">
              In the temporary saved docs folder, not this client&apos;s own folder. It moves into the client&apos;s attendance notes folder by itself once that folder exists.
            </span>
          )}
          {item.state === "failed" && (
            <span className="an-recent-state an-recent-state--failed" role="alert">
              Not filed: {item.error || "something went wrong."} The note is saved.{" "}
              {onEdit && (
                <button
                  type="button"
                  className="cf-btn cf-btn--neutral cf-btn--small"
                  disabled={editing === item.draft_id}
                  onClick={() => void edit(item.draft_id)}
                >
                  Edit
                </button>
              )}{" "}
              <button
                type="button"
                className="cf-btn cf-btn--neutral cf-btn--small"
                disabled={retrying === item.draft_id}
                onClick={() => void retry(item.draft_id)}
              >
                Try again
              </button>
              {editError?.id === item.draft_id && <span className="an-recent-error" role="alert"> {editError.message}</span>}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
