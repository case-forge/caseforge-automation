"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  confirmedByWords,
  createPayloadFromForm,
  describeEdits,
  durationLabel,
  editsFromForm,
  emptyFormValues,
  formFromHearing,
  formatDateShort,
  formatTime12,
  hearingLabel,
  hearingParties,
  HEARING_MODES,
  isUnlinked,
  linkOutcomeMessage,
  safeHttpUrl,
  sourceKindLabel,
  requestLabel,
  statusLabel,
  vacatedSummary,
  validateHearingForm,
  visibleConfidence,
} from "@/lib/hearings";
import type { Hearing, HearingFormValues, HearingHistoryEvent } from "@/lib/hearings";
import { createHearing, fetchHearingHistory, isAbort, resolveReview, unlinkHearing, updateHearing } from "@/lib/hearingsClient";
import { HearingBadges } from "./HearingBadges";
import { HearingStateActions } from "./HearingStateActions";
import { DuplicateHearingNotice } from "./DuplicateHearingNotice";
import { HearingForm } from "./HearingForm";
import { LinkToClient } from "./LinkToClient";
import { IconClose } from "./icons";
import { hearingsHost } from "@/lib/hearingsHost";
import { hearingToast } from "@/lib/hearingToast";
import { confirmDiscardUnsaved, confirmLeaveUnsaved, useCurrentClient, useReportUnsaved } from "@/lib/unsavedEdits";
import type { UnsavedSource } from "@/lib/unsavedEdits";
import { changedValues, useFormDraft } from "@/lib/formDrafts";
import { DraftRestoredNote } from "./DraftRestoredNote";
import { deleteHearingDraft, draftLabel, hasDraftContent, saveHearingDraft } from "@/lib/hearingDrafts";

function useHearingSource(label: string, matterId: string | number | null | undefined, clientName?: string | null): Omit<UnsavedSource, "id"> {
  const client = useCurrentClient();
  const matter = matterId == null || String(matterId).trim() === "" ? undefined : String(matterId).trim();
  const onPanel = !!client && !!matter && client.matterId === matter;
  return {
    label,
    matterId: matter,
    clientName: onPanel ? client.clientName : clientName?.trim() || undefined,
    place: onPanel ? client.tab : undefined,
    persistent: true,
  };
}

function DrawerShell({
  title,
  badges,
  onClose: closeNow,
  onEscape,
  beforeClose,
  label,
  guardId,
  bare = false,
  children,
}: {

  bare?: boolean;

  guardId: string;
  title: string;
  badges?: ReactNode;
  onClose: () => void;

  onEscape?: () => boolean;

  beforeClose?: () => boolean;
  label: string;
  children: ReactNode;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const onClose = () => {
    if ((beforeClose ?? (() => confirmLeaveUnsaved([guardId])))()) closeNow();
  };

  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    opener.current = document.activeElement as HTMLElement | null;
    return () => {
      const previous = opener.current;
      if (previous && previous !== document.body && document.contains(previous)) previous.focus();
    };
  }, []);
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  if (bare) {
    return (
      <section className="hearing-pane hearing-pane--tab" data-unsaved-source={guardId} role="group" aria-label={label}>
        <div className="hearing-drawer-body">{children}</div>
      </section>
    );
  }

  return (
    <section
      className="hearing-pane"
      data-unsaved-source={guardId}
      role="dialog"
      aria-label={label}
      onKeyDown={(e) => {
        if (e.key !== "Escape") return;
        e.stopPropagation();
        if (onEscape?.()) return;
        onClose();
      }}
    >
      <header className="hearing-drawer-head">
        <div className="hearing-drawer-titles">
          <h2 className="hearing-drawer-title" tabIndex={-1} ref={headingRef}>
            {title}
          </h2>
          {badges && <div className="hearing-drawer-badges">{badges}</div>}
        </div>
        <button type="button" className="cf-btn cf-btn--icon cf-btn--compact" aria-label={`Close ${title}`} title="Close" onClick={onClose}>
          <IconClose aria-hidden="true" />
        </button>
      </header>
      <div className="hearing-drawer-body">{children}</div>
    </section>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="hearing-fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function modeLabel(mode: string): string {
  return HEARING_MODES.find((m) => m.value === mode)?.label ?? mode;
}

function receivedLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function describeHistoryEvent(event: HearingHistoryEvent): string {
  const after = event.after && typeof event.after === "object" ? (event.after as Record<string, unknown>) : null;
  const actions: Record<string, string> = {
    created: "Created",
    updated: "Edited",
    status: "Status changed",
    linked: "Linked to a client",
    review_confirmed: "Review confirmed",
    review_dismissed: "Review dismissed",
    moved: "Moved to a new date or time",
    request: "Request to the court",
  };
  const label = actions[event.action] ?? event.action;
  if (!after) return label;
  const fields = Object.keys(after).filter((key) => key !== "source");
  return fields.length ? `${label}: ${fields.join(", ")}` : label;
}

interface HearingDrawerProps {
  hearing: Hearing;
  onClose: () => void;

  onChanged: (hearing: Hearing) => void;

  onOpenClient?: (hearing: Hearing) => void;

  startEditing?: boolean;
}

export const hearingWindowId = (h: Hearing): string => `hearing-edit-${h.hearing_id}`;
export const hearingWindowTitle = (h: Hearing): string => `${hearingLabel(h)} - ${hearingParties(h)}`;

export function HearingDrawer(props: HearingDrawerProps) {
  return <HearingDrawerBody key={props.hearing.hearing_id} {...props} />;
}

function HearingDrawerBody({ hearing, onClose, onChanged, onOpenClient, startEditing }: HearingDrawerProps) {
  const [editing, setEditing] = useState(!!startEditing);
  const firstReset = useRef(true);
  const [form, setForm] = useState<HearingFormValues>(() => formFromHearing(hearing));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HearingHistoryEvent[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const historyController = useRef<AbortController | null>(null);

  const [linkNotice, setLinkNotice] = useState<{ hearingId: number; message: string } | null>(null);

  useEffect(() => {

    setEditing(firstReset.current && !!startEditing);
    firstReset.current = false;
    setForm(formFromHearing(hearing));
    setError(null);
    setHistory(null);
    setHistoryError(null);
  }, [hearing]);

  useEffect(() => {
    setLinkNotice((current) => (current && current.hearingId !== hearing.hearing_id ? null : current));
  }, [hearing.hearing_id]);

  const dirty = editing && JSON.stringify(form) !== JSON.stringify(formFromHearing(hearing));

  const guardId = hearingWindowId(hearing);
  useReportUnsaved(guardId, useHearingSource("Hearing", hearing.matter_id, hearing.client_name), dirty);

  useEffect(() => hearingsHost.registerGuard(guardId, () => confirmLeaveUnsaved([guardId])), [guardId]);
  const kept = useFormDraft<Partial<HearingFormValues>>({
    matterId: hearing.matter_id,
    formId: guardId,
    server: true,
    dirty,
    data: changedValues(form, formFromHearing(hearing)),
    restore: (changes) => {
      setForm({ ...formFromHearing(hearing), ...changes });
      setEditing(true);
    },
  });
  function cancelEdit() {
    setEditing(false);
    setForm(formFromHearing(hearing));
    setError(null);
  }

  const noticeRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (linkNotice) noticeRef.current?.focus();
  }, [linkNotice]);

  useEffect(() => () => historyController.current?.abort(), []);

  const check = validateHearingForm(form, { requireCaseRef: false });
  const label = hearingLabel(hearing);
  const parties = hearingParties(hearing);
  const joinUrl = safeHttpUrl(hearing.join_url);
  const sourceLink = safeHttpUrl(hearing.source_web_link);

  async function run(action: () => Promise<{ hearing: Hearing }>) {
    setBusy(true);
    setError(null);
    try {
      const body = await action();
      onChanged(body.hearing);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the change");
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (Object.keys(check.errors).length) {
      setError("Fix the highlighted fields first.");
      return;
    }
    const edits = editsFromForm(hearing, form);
    if (Object.keys(edits).length === 0) {
      setEditing(false);
      return;
    }
    const summary = describeEdits(edits).join("\n");
    if (!window.confirm(`Apply ${Object.keys(edits).length} change${Object.keys(edits).length === 1 ? "" : "s"}?\n\n${summary}`)) return;
    void run(() => updateHearing(hearing.hearing_id, edits));
  }

  function unlink() {
    if (!window.confirm(`Unlink this hearing from ${hearing.client_name ?? "its client"}? It will not be linked again automatically.`)) return;
    void run(() => unlinkHearing(hearing.hearing_id));
  }

  function loadHistory() {
    if (history !== null) return;
    historyController.current?.abort();
    const controller = new AbortController();
    historyController.current = controller;
    setHistoryError(null);
    fetchHearingHistory(hearing.hearing_id, controller.signal)
      .then((body) => setHistory(body.events))
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setHistoryError(err instanceof Error ? err.message : "Could not load the history");
      });
  }

  return (
    <DrawerShell
      guardId={guardId}
      title={hearingWindowTitle(hearing)}
      badges={<HearingBadges hearing={hearing} />}
      label={`Hearing: ${label}, ${parties}`}
      onClose={onClose}
      onEscape={() => {
        if (!editing) return false;

        if (!confirmDiscardUnsaved([guardId])) return true;
        cancelEdit();
        return true;
      }}
    >
      {linkNotice && linkNotice.hearingId === hearing.hearing_id && (
        <p className="hearing-link-notice" role="status" tabIndex={-1} ref={noticeRef}>
          {linkNotice.message}
        </p>
      )}

      {hearing.review_state === "needs_review" && (
        <section className="hearing-review-box" aria-label="Needs review">
          <p className="hearing-review-reason">{hearing.review_reason || "This hearing needs a decision."}</p>
          <div className="hearing-actions">
            <button
              type="button"
              className="cf-btn cf-btn--primary"
              disabled={busy}
              onClick={() => void run(() => resolveReview(hearing.hearing_id, "confirm"))}
            >
              Confirm as it is
            </button>
            <button
              type="button"
              className="cf-btn cf-btn--flush"
              disabled={busy}
              onClick={() => {
                if (!window.confirm("Dismiss this hearing? It leaves the calendar and the queue; the history is kept.")) return;
                void run(() => resolveReview(hearing.hearing_id, "dismiss"));
              }}
            >
              Dismiss
            </button>
          </div>
        </section>
      )}

      {editing ? (
        <div className="hearing-edit">
          <DraftRestoredNote savedAt={kept.restoredAt} saveLabel="Save changes" onDiscard={cancelEdit} />
          <HearingForm values={form} onChange={setForm} errors={check.errors} warnings={check.warnings} idPrefix="edit" disabled={busy} />
          <div className="hearing-actions">
            <button type="button" className="cf-btn cf-btn--primary" disabled={busy} onClick={save}>
              Save changes
            </button>
            <button
              type="button"
              className="cf-btn cf-btn--flush"
              disabled={busy}
              onClick={cancelEdit}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <dl className="hearing-facts">
            <Fact label="Date">{formatDateShort(hearing.hearing_date)}</Fact>
            <Fact label="Time">{formatTime12(hearing.hearing_time)}</Fact>
            <Fact label="Duration">{durationLabel(hearing)}</Fact>
            <Fact label="Status">{vacatedSummary(hearing) || requestLabel(hearing) || statusLabel(hearing.status)}</Fact>
            <Fact label="Court">{hearing.court || "Not stated"}</Fact>
            <Fact label="Mode">{hearing.mode ? modeLabel(hearing.mode) : "Not stated"}</Fact>
            {joinUrl && (
              <Fact label="Join link">
                <a href={joinUrl} target="_blank" rel="noreferrer">
                  Open the meeting link
                </a>
              </Fact>
            )}
            <Fact label="Hearing type">{hearing.hearing_type || "Not stated"}</Fact>
            <Fact label="Order types">{hearing.order_types || "Not stated"}</Fact>
            <Fact label="Case number">{hearing.case_ref || "Not stated"}</Fact>
            <Fact label="Client">
              {hearing.client_name ? hearing.client_name : "Not linked to a client"}
              {onOpenClient && (hearing.case_ref || hearing.client_name) && (
                <>
                  {" "}
                  <button type="button" className="cf-btn cf-btn--link hearing-link-button" onClick={() => onOpenClient(hearing)}>
                    Open client
                  </button>
                </>
              )}
              {hearing.matter_id !== null && hearing.client_name && (
                <>
                  {" "}
                  <button type="button" className="cf-btn cf-btn--link hearing-link-button" disabled={busy} onClick={unlink}>
                    Unlink
                  </button>
                </>
              )}
            </Fact>
            {(hearing.applicant || hearing.respondent) && (
              <Fact label="Parties">{[hearing.applicant, hearing.respondent].filter(Boolean).join(" v ")}</Fact>
            )}
            {hearing.counsel && <Fact label="Counsel">{hearing.counsel}</Fact>}
            {hearing.chambers && <Fact label="Chambers">{hearing.chambers}</Fact>}
            {hearing.notes && <Fact label="Notes">{hearing.notes}</Fact>}
          </dl>

          <section className="hearing-source" aria-label="Source">
            <h3 className="detail-section-title">Where this came from</h3>
            <p>
              {sourceKindLabel(hearing.source_kind)}
              {hearing.source_received_utc ? `, received ${receivedLabel(hearing.source_received_utc)}` : ""}
              {visibleConfidence(hearing) !== null ? `, confidence ${Math.round((visibleConfidence(hearing) ?? 0) * 100)}%` : ""}
              {confirmedByWords(hearing)}
            </p>
            {hearing.source_subject && <p className="hearing-source-subject">Re: {hearing.source_subject}</p>}
            {sourceLink && (
              <a href={sourceLink} target="_blank" rel="noreferrer">
                Open the source email
              </a>
            )}
          </section>

          {isUnlinked(hearing) && (
            <LinkToClient
              hearing={hearing}
              onError={setError}
              onLinked={(result, clientName) => {
                setLinkNotice({
                  hearingId: hearing.hearing_id,
                  message: linkOutcomeMessage(result.reference, result.hearing.case_ref || hearing.case_ref, clientName),
                });
                onChanged(result.hearing);
              }}
            />
          )}

          <HearingStateActions hearing={hearing} busy={busy} onEdit={() => setEditing(true)} run={run} onError={setError} />

          <details className="hearing-history" onToggle={(e) => e.currentTarget.open && loadHistory()}>
            <summary>History</summary>
            {historyError && <p className="hearing-form-error" role="alert">{historyError}</p>}
            {history === null && !historyError && <p className="hearing-muted">Loading...</p>}
            {history !== null && history.length === 0 && <p className="hearing-muted">No changes recorded.</p>}
            {history !== null && history.length > 0 && (
              <ol className="hearing-history-list">
                {history.map((event) => (
                  <li key={event.event_id}>
                    <span className="hearing-history-what">{describeHistoryEvent(event)}</span>
                    <span className="hearing-history-meta">
                      {event.actor} - {receivedLabel(event.at)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </details>
        </>
      )}

      {error && (
        <p className="hearing-form-error" role="alert">
          {error}
        </p>
      )}
    </DrawerShell>
  );
}

export function NewHearingDrawer({
  defaults,
  onClose,
  onCreated,
  intro,
  known,
  onEditExisting,
  guardId = "hearing-new",
  clientName,
  draftId,
  restoreValues,
  bare = false,
}: {

  bare?: boolean;

  draftId?: string;

  restoreValues?: Partial<HearingFormValues>;

  guardId?: string;

  clientName?: string;

  known?: Hearing[];

  onEditExisting?: (hearing: Hearing) => void;
  defaults?: Partial<HearingFormValues>;
  onClose: () => void;

  onCreated: (hearing: Hearing) => void;

  intro?: string;
}) {
  const [form, setForm] = useState<HearingFormValues>(() => ({ ...emptyFormValues(defaults), ...restoreValues }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [submitted, setSubmitted] = useState(false);
  const check = validateHearingForm(form, { requireCaseRef: true });
  const dirty = JSON.stringify(form) !== JSON.stringify(emptyFormValues(defaults));
  const matterId = defaults?.matter_id || "";
  useReportUnsaved(guardId, useHearingSource("New hearing", matterId, clientName), dirty);

  const kept = useFormDraft<Partial<HearingFormValues>>({
    matterId,
    formId: guardId,
    dirty,
    data: changedValues(form, emptyFormValues(defaults)),
    restore: (changes) => setForm({ ...emptyFormValues(defaults), ...changes }),
  });
  function cancel() {
    kept.clear();
    onClose();
  }

  function keepAsDraft(): boolean {
    const values = changedValues(form, emptyFormValues(defaults));
    if (!hasDraftContent(values)) return false;

    const when = { ...(form.hearing_date ? { hearing_date: form.hearing_date } : {}), ...(form.hearing_time ? { hearing_time: form.hearing_time } : {}) };
    const saved = saveHearingDraft({ id: draftId, matterId, clientName, values: { ...values, ...when, ...(matterId ? { matter_id: matterId } : {}) } });
    kept.clear();
    hearingToast.show(`Kept as a draft: ${draftLabel(saved)}. It is on the calendar and in the client's Hearings tab, and Continue picks it up.`);
    return true;
  }
  function saveToDrafts() {
    if (!keepAsDraft()) {
      setError("Type something first: there is nothing to keep yet.");
      return;
    }
    onClose();
  }

  const guard = useRef<() => boolean>(() => true);
  useEffect(() => {
    guard.current = () => (hasDraftContent(changedValues(form, emptyFormValues(defaults))) ? keepAsDraft() : true);
  });
  useEffect(() => hearingsHost.registerGuard(guardId, () => guard.current()), [guardId]);

  async function submit() {
    setSubmitted(true);
    if (Object.keys(check.errors).length) {
      setError("Fix the highlighted fields first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = await createHearing(createPayloadFromForm(form));
      kept.clear();
      if (draftId) deleteHearingDraft(draftId);
      onCreated(body.hearing);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the hearing");
    } finally {
      setBusy(false);
    }
  }

  return (
    <DrawerShell guardId={guardId} bare={bare} title={clientName ? `Add a Hearing: ${clientName}` : "Add a Hearing"} label="Add a Hearing" onClose={onClose} beforeClose={() => guard.current()}>
      <p className="hearing-muted">
        {intro ?? "Use this for a hearing that did not arrive by email. It is recorded as entered by hand."}
        {draftId ? " This is a saved draft: it is not a hearing until you add it." : ""}
      </p>
      <DraftRestoredNote savedAt={kept.restoredAt} saveLabel="Add hearing" onDiscard={() => setForm(emptyFormValues(defaults))} />
      <DuplicateHearingNotice form={form} known={known} onEditExisting={onEditExisting} />
      <HearingForm
        values={form}
        onChange={setForm}
        errors={submitted ? check.errors : {}}
        warnings={check.warnings}
        idPrefix="new"
        disabled={busy}
        autoFocusField="case_ref"
      />
      <div className="hearing-actions">
        <button type="button" className="cf-btn cf-btn--primary" disabled={busy} onClick={() => void submit()}>
          Add hearing
        </button>
        <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={saveToDrafts}>
          Save to drafts
        </button>
        <button type="button" className="cf-btn cf-btn--flush" disabled={busy} onClick={cancel}>
          Cancel
        </button>
      </div>
      {error && (
        <p className="hearing-form-error" role="alert">
          {error}
        </p>
      )}
    </DrawerShell>
  );
}
