"use client";

import { useEffect, useRef, useState } from "react";
import { formatDateShort, formatTime12, hearingLabel, HEARING_MODES, isVacated, requestLabel } from "@/lib/hearings";
import type { Hearing, HearingFormValues } from "@/lib/hearings";
import { hearingsAndUpdates } from "@/lib/hearingsTimeline";
import type { MatterHearingsState } from "@/lib/useHearings";
import type { MatterTasksResponse } from "@/lib/types";
import { HearingBadges } from "./HearingBadges";
import { hearingsHost, useHearingsVersion } from "@/lib/hearingsHost";
import { useCurrentClient } from "@/lib/unsavedEdits";
import { UpdateCounts, UpdateRow } from "./MatterTasks";
import { deleteHearingDraft, draftsForMatter, useHearingDrafts } from "@/lib/hearingDrafts";
import type { HearingDraft } from "@/lib/hearingDrafts";

function DraftRow({ draft, known }: { draft: HearingDraft; known: Hearing[] }) {
  const date = String(draft.values.hearing_date ?? "");
  const time = String(draft.values.hearing_time ?? "");
  const what = [date ? formatDateShort(date) : "No date yet", time ? formatTime12(time) : "", String(draft.values.court ?? "")].filter(Boolean).join(", ");
  return (
    <div className="matter-draft" role="listitem" data-draft-id={draft.id}>
      <span className="hearing-badge hearing-badge--draft">Draft</span>
      <span className="matter-draft-text">{what}</span>
      <span className="matter-draft-actions">
        <button type="button" className="cf-btn cf-btn--secondary" onClick={() => hearingsHost.openDraft(draft, known)}>
          Continue
        </button>
        <button type="button" className="cf-btn cf-btn--flush" onClick={() => deleteHearingDraft(draft.id)}>
          Discard
        </button>
      </span>
    </div>
  );
}

function modeText(mode: string): string {
  return mode ? (HEARING_MODES.find((m) => m.value === mode)?.label ?? mode) : "";
}

const FOCUS_HIGHLIGHT_MS = 6000;

function HearingRow({ hearing, focused, onOpen }: { hearing: Hearing; focused: boolean; onOpen: (h: Hearing) => void }) {
  const muted = isVacated(hearing);
  const requested = requestLabel(hearing);
  const mode = modeText(hearing.mode);
  return (
    <li className="matter-timeline-hearing" data-hearing-id={hearing.hearing_id} data-focused={focused || undefined}>
      <button
        type="button"
        className={`matter-hearing-row${muted ? " matter-hearing-row--muted" : ""}${requested ? " matter-hearing-row--request" : ""}`}
        onClick={() => onOpen(hearing)}
        aria-label={`Hearing, ${formatDateShort(hearing.hearing_date)}, ${formatTime12(hearing.hearing_time)}, ${hearingLabel(hearing)}${hearing.court ? `, ${hearing.court}` : ""}${muted ? ", vacated" : ""}${requested ? `, ${requested.toLowerCase()}` : ""}. Open hearing`}
      >
        <span className="matter-hearing-when">
          <span className="matter-hearing-kind">Hearing</span>
          <span className="matter-hearing-date">{formatDateShort(hearing.hearing_date)}</span>
          <span className="matter-hearing-time">{formatTime12(hearing.hearing_time)}</span>
        </span>
        <span className="matter-hearing-what">
          <span className="matter-hearing-label">{hearingLabel(hearing)}</span>
          {hearing.hearing_type && hearing.hearing_type.trim() !== hearingLabel(hearing) && (
            <span className="matter-hearing-type">{hearing.hearing_type}</span>
          )}
          <span className="matter-hearing-court">{[hearing.court, mode].filter(Boolean).join(" - ") || "Court not stated"}</span>
        </span>
        <span className="matter-hearing-badges">
          <HearingBadges hearing={hearing} />
        </span>
      </button>
    </li>
  );
}

export interface FocusHearing {
  hearingId: number;
  nonce: number;
}

export function HearingsUpdatesTab({
  state,
  caseRef,
  tasks,
  focusHearing,
  view,
}: {

  view: "hearings" | "updates";
  state: MatterHearingsState;

  caseRef: string;
  tasks: MatterTasksResponse | null;
  focusHearing?: FocusHearing | null;
}) {
  const { matterId, hearings, loading, error, loaded, refresh } = state;

  const client = useCurrentClient();
  const writes = useHearingsVersion();
  useEffect(() => {
    if (writes > 0) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [writes]);
  const matterDrafts = draftsForMatter(useHearingDrafts(), String(matterId ?? ""));
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const focusedNonce = useRef(0);

  const focusPresent =
    view === "hearings" && focusHearing != null && hearings.some((h) => h.hearing_id === focusHearing.hearingId && h.review_state !== "dismissed");
  useEffect(() => {
    if (!focusHearing || !focusPresent || focusHearing.nonce === focusedNonce.current) return;
    const row = listRef.current?.querySelector<HTMLElement>(`[data-hearing-id="${focusHearing.hearingId}"]`);
    if (!row) return;
    focusedNonce.current = focusHearing.nonce;
    setFocusedId(focusHearing.hearingId);
    row.scrollIntoView?.({ block: "center", behavior: "smooth" });
    row.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  }, [focusHearing, focusPresent]);
  useEffect(() => {
    if (focusedId === null) return;
    const timer = window.setTimeout(() => setFocusedId(null), FOCUS_HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [focusedId, focusHearing?.nonce]);

  if (matterId === null) {
    return <p className="hearing-muted matter-hearings-empty">No matter record yet, so there is nothing to show here.</p>;
  }

  const items = tasks?.configured ? tasks.items : [];
  const entries = hearingsAndUpdates(hearings, items).filter((entry) => entry.kind === (view === "hearings" ? "hearing" : "update"));
  const hasUpdates = entries.some((entry) => entry.kind === "update");
  const tasksStatus = view !== "updates" ? "" : !tasks ? "Loading updates…" : !tasks.configured ? "Updates could not be read just now. Try reopening this client." : "";
  const everythingRead = view === "hearings" ? loaded : tasks !== null;
  const defaults: Partial<HearingFormValues> = { matter_id: String(matterId), case_ref: caseRef };
  const now = new Date();

  return (
    <section className="matter-hearings matter-timeline" aria-label={view === "hearings" ? "Hearings for this client" : "Updates for this client"}>
      <div className="matter-hearings-head">
        <h3 className="detail-section-title matter-tasks-title">
          {view === "hearings" ? "Hearings" : "Updates"}
          {view === "updates" && <UpdateCounts tasks={tasks} />}
        </h3>
        {view === "hearings" && (
          <button type="button" className="cf-btn cf-btn--primary" onClick={() =>
              hearingsHost.openCreate({
                matterId: String(matterId),
                clientName: client?.matterId === String(matterId) ? client.clientName : undefined,
                defaults,
                known: hearings,
                intro: caseRef ? undefined : "This client's record has no single court number, so type it in.",
              })
            }>
            Add hearing for this client
          </button>
        )}
      </div>

      {view === "hearings" && matterDrafts.length > 0 && (
        <div className="matter-drafts" role="list" aria-label="Hearing drafts for this client">
          {matterDrafts.map((d) => (
            <DraftRow key={d.id} draft={d} known={hearings} />
          ))}
        </div>
      )}
      {view === "hearings" && error && <p className="hearing-form-error" role="alert">{error}</p>}
      {view === "hearings" && loading && !loaded && <p className="hearing-muted">Loading hearings...</p>}
      {tasksStatus && <p className="hearing-muted matter-tasks-empty">{tasksStatus}</p>}
      {everythingRead && entries.length === 0 && (
        <p className="hearing-muted matter-hearings-empty">
          {view === "hearings" ? "No hearings recorded for this client yet." : "No complaints, settlements or updates for this client yet."}
        </p>
      )}

      {entries.length > 0 && (
        <ul className="matter-timeline-list" ref={listRef}>
          {entries.map((entry) =>
            entry.kind === "hearing" ? (
              <HearingRow key={entry.key} hearing={entry.hearing} focused={focusedId === entry.hearing.hearing_id} onOpen={(h) => hearingsHost.openEdit(h)} />
            ) : (
              <UpdateRow key={entry.key} item={entry.item} now={now} />
            ),
          )}
        </ul>
      )}
      {hasUpdates && <p className="matter-tasks-note">AI-drafted summaries of the email text. Open the email to verify before acting.</p>}

    </section>
  );
}
