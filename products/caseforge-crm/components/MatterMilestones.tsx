"use client";

import { useState } from "react";
import { GRAPH_READ_CACHE_MS, useLazyFetch } from "@/lib/useLazyFetch";
import {
  MILESTONES,
  fromLocalInputValue,
  milestoneSourceNote,
  milestoneTime,
  toLocalInputValue,
  type MatterMilestonesResponse,
  type MilestoneKey,
  type MilestoneValue,
} from "@/lib/matterMilestones";
import { IconCheck } from "./icons";
import { safeBoardLink } from "@/lib/boardLinks";

type State = "received" | "missing" | "unknown" | "loading";

interface RowProps {
  label: string;
  title: string;
  value: MilestoneValue | undefined;
  state: State;

  onSave: ((at: string, clear: boolean) => Promise<string>) | null;
}

function MilestoneRow({ label, title, value, state, onSave }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const shown = state === "received" && value ? milestoneTime(value.at) : "";
  const text = state === "loading" ? "Checking…" : state === "unknown" ? "Couldn't check" : state === "received" ? shown || "Recorded" : "Not yet";

  async function save(at: string, clear: boolean) {
    if (!onSave) return;
    setBusy(true);
    setError("");
    const problem = await onSave(at, clear);
    setBusy(false);
    if (problem) setError(problem);
    else setEditing(false);
  }

  return (
    <div className="detail-field matter-marker matter-milestone" data-state={state}>
      <p className="detail-field-label" title={title}>
        {label}
      </p>
      <p className="matter-marker-value" title={milestoneSourceNote(value)}>
        <span className="matter-marker-box" aria-hidden="true">
          {state === "received" && <IconCheck width={13} height={13} strokeWidth={3} />}
        </span>
        <span>
          {state === "received" && safeBoardLink(value?.link) ? (
            <a className="board-date-link" href={safeBoardLink(value?.link)} target="_blank" rel="noopener noreferrer">
              {text}
              <span className="sr-only"> (opens the {label === "LAA final cert" || label === "Papers signed" || label === "LAA interim cert" ? "file" : "email"} in a new tab)</span>
            </a>
          ) : (
            text
          )}
        </span>
      </p>
      {onSave && (state === "received" || state === "missing") && !editing && (
        <p className="matter-milestone-actions">
          <button
            type="button"
            className="cf-btn cf-btn--neutral cf-btn--small matter-milestone-btn"
            onClick={() => {
              setDraft(toLocalInputValue(new Date(state === "received" && value?.at ? value.at : Date.now())));
              setError("");
              setEditing(true);
            }}
          >
            {state === "received" ? "Change" : "Record"}
          </button>
          {state === "received" && (
            <button type="button" className="cf-btn cf-btn--neutral cf-btn--small matter-milestone-btn" disabled={busy} onClick={() => void save("", true)}>
              Clear
            </button>
          )}
        </p>
      )}
      {onSave && editing && (
        <p className="matter-milestone-actions">
          <input
            type="datetime-local"
            className="matter-milestone-input"
            aria-label={`${label}: date and time`}
            value={draft}
            max={toLocalInputValue(new Date())}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="button" className="cf-btn cf-btn--neutral cf-btn--small matter-milestone-btn" disabled={busy || !fromLocalInputValue(draft)} onClick={() => void save(fromLocalInputValue(draft), false)}>
            Save
          </button>
          <button type="button" className="cf-btn cf-btn--neutral cf-btn--small matter-milestone-btn" disabled={busy} onClick={() => setEditing(false)}>
            Cancel
          </button>
        </p>
      )}
      {error && <p className="matter-milestone-error" role="alert">{error}</p>}
    </div>
  );
}

export function MatterMilestones({ matterId }: { matterId: string }) {
  const { data, failed, setData } = useLazyFetch<MatterMilestonesResponse>(
    matterId ? `/api/clients/matter-milestones?matter_id=${encodeURIComponent(matterId)}&live=1` : null,
    { cacheMs: GRAPH_READ_CACHE_MS },
  );

  async function saveFor(key: MilestoneKey, at: string, clear: boolean): Promise<string> {
    try {
      const res = await fetch("/api/clients/matter-milestones", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter_id: matterId, milestone: key, at, clear }),
      });
      const body = (await res.json().catch(() => ({}))) as Partial<MatterMilestonesResponse> & { error?: string; detail?: string };
      if (!res.ok || !body.milestones) return String(body.error ?? body.detail ?? "That could not be saved.");
      setData({ matter_id: matterId, milestones: body.milestones });
      return "";
    } catch {
      return "That could not be saved: the connection dropped.";
    }
  }

  return (
    <>
      {MILESTONES.map(({ key, label, title }) => {
        const value = data?.milestones?.[key];
        const state: State = failed || !matterId ? "unknown" : !data ? "loading" : value?.at ? "received" : "missing";
        return (
          <MilestoneRow
            key={key}
            label={label}
            title={title}
            value={value}
            state={state}
            onSave={value?.can_set ? (at, clear) => saveFor(key, at, clear) : null}
          />
        );
      })}
    </>
  );
}
