"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import {
  editsFromForm,
  filterHearings,
  formatDateShort,
  formatTime12,
  formFromHearing,
  hearingLabel,
  hearingParties,
  safeHttpUrl,
  validateHearingForm,
} from "@/lib/hearings";
import type { Hearing, HearingEdits, HearingFormValues } from "@/lib/hearings";
import { fetchReviewQueue, isAbort, resolveReview } from "@/lib/hearingsClient";
import { HearingBadges } from "./HearingBadges";
import { HearingForm } from "./HearingForm";
import { IconAlert } from "./icons";

export function ReviewQueue({
  refreshKey,
  onChanged,
  onOpen,
  filter = "",
}: {
  refreshKey: number;

  filter?: string;

  onChanged: () => void;
  onOpen: (hearing: Hearing) => void;
}) {
  const [items, setItems] = useState<Hearing[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<HearingFormValues | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const shown = items ? filterHearings(items, filter) : null;

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    fetchReviewQueue(controller.signal)
      .then((body) => setItems(body.hearings))
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setLoadError(err instanceof Error ? err.message : "Could not load the review queue");
      });
    return () => controller.abort();
  }, [refreshKey]);

  function focusRow(id: number | undefined) {
    if (id === undefined) return;
    window.setTimeout(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-review-id="${id}"]`)?.focus();
    }, 0);
  }

  async function resolve(hearing: Hearing, action: "confirm" | "dismiss", edits?: HearingEdits) {
    setBusyId(hearing.hearing_id);
    setRowError(null);
    try {
      await resolveReview(hearing.hearing_id, action, edits);
      const list = items ?? [];
      const index = list.findIndex((h) => h.hearing_id === hearing.hearing_id);
      const next = list[index + 1] ?? list[index - 1];
      setItems(list.filter((h) => h.hearing_id !== hearing.hearing_id));
      setEditingId(null);
      setForm(null);
      onChanged();
      focusRow(next?.hearing_id);
    } catch (err) {
      setRowError({ id: hearing.hearing_id, message: err instanceof Error ? err.message : "Could not save the decision" });
    } finally {
      setBusyId(null);
    }
  }

  function confirmDismiss(hearing: Hearing) {
    if (!window.confirm("Dismiss this hearing? It leaves the calendar and the queue; the history is kept.")) return;
    void resolve(hearing, "dismiss");
  }

  function startEdit(hearing: Hearing) {
    setEditingId(hearing.hearing_id);
    setForm(formFromHearing(hearing));
    setRowError(null);
  }

  function saveEdit(hearing: Hearing) {
    if (!form) return;
    const check = validateHearingForm(form, { requireCaseRef: false });
    if (Object.keys(check.errors).length) {
      setRowError({ id: hearing.hearing_id, message: "Fix the highlighted fields first." });
      return;
    }
    void resolve(hearing, "confirm", editsFromForm(hearing, form));
  }

  function onKeyDown(e: KeyboardEvent<HTMLUListElement>) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const target = e.target as HTMLElement;
    if (target.closest("input, textarea, select")) return;
    const row = target.closest<HTMLElement>("[data-review-id]");
    if (!row || !shown) return;
    const id = Number(row.dataset.reviewId);
    const index = shown.findIndex((h) => h.hearing_id === id);
    const hearing = shown[index];
    if (!hearing || busyId !== null) return;

    switch (e.key) {
      case "ArrowDown":
      case "j":
        e.preventDefault();
        focusRow(shown[index + 1]?.hearing_id);
        break;
      case "ArrowUp":
      case "k":
        e.preventDefault();
        focusRow(shown[index - 1]?.hearing_id);
        break;
      case "c":
        e.preventDefault();
        void resolve(hearing, "confirm");
        break;
      case "d":
        e.preventDefault();
        confirmDismiss(hearing);
        break;
      case "e":
        e.preventDefault();
        startEdit(hearing);
        break;
      case "o":
        e.preventDefault();
        onOpen(hearing);
        break;
    }
  }

  if (loadError) {
    return (
      <p className="hearing-form-error" role="alert">
        {loadError}
      </p>
    );
  }
  if (items === null) return <p className="hearing-muted">Loading the review queue...</p>;

  return (
    <section className="review-queue" aria-label="Hearings needing review">
      <h3 className="review-section-title">Hearings to review</h3>
      <div className="review-queue-head">
        <p className="hearing-muted review-queue-hint">
          {items.length === 0
            ? "No hearings need review."
            : `${filter.trim() ? `${shown?.length ?? 0} of ${items.length}` : items.length} to review. Keys: j and k move, c confirms, e edits, d dismisses, o opens the detail.`}
        </p>
      </div>

      <ul className="review-list" ref={listRef} onKeyDown={onKeyDown}>
        {(shown ?? []).map((hearing) => {
          const label = hearingLabel(hearing);
          const parties = hearingParties(hearing);
          const link = safeHttpUrl(hearing.source_web_link);
          const editing = editingId === hearing.hearing_id && form !== null;
          const busy = busyId === hearing.hearing_id;
          const check = editing && form ? validateHearingForm(form, { requireCaseRef: false }) : null;
          return (
            <li
              key={hearing.hearing_id}
              className="review-row"
              data-review-id={hearing.hearing_id}
              tabIndex={0}
              aria-label={`${label}, ${parties}, ${formatDateShort(hearing.hearing_date)}, needs review`}
              aria-busy={busy || undefined}
            >
              <div className="review-row-main">
                <div className="review-row-title">
                  <strong>{label}</strong>
                  <span>{parties}</span>
                  <HearingBadges hearing={hearing} />
                </div>
                <p className="review-row-facts">
                  {formatDateShort(hearing.hearing_date)} - {formatTime12(hearing.hearing_time)} - {hearing.court || "Court not stated"} -{" "}
                  {hearing.case_ref || "No case number"}
                </p>
                <p className="review-row-reason">
                  <IconAlert className="review-row-reason-icon" aria-hidden="true" />
                  <span>{hearing.review_reason || "This hearing needs a decision."}</span>
                </p>
                {(hearing.source_subject || link) && (
                  <p className="review-row-source">
                    {hearing.source_subject && <>Re: {hearing.source_subject} </>}
                    {link && (
                      <a href={link} target="_blank" rel="noreferrer">
                        Open the source email
                      </a>
                    )}
                  </p>
                )}
              </div>

              {editing && form && check ? (
                <div className="review-row-edit">
                  <HearingForm values={form} onChange={setForm} errors={check.errors} warnings={check.warnings} idPrefix={`review-${hearing.hearing_id}`} disabled={busy} />
                  <div className="hearing-actions">
                    <button type="button" className="cf-btn cf-btn--primary" disabled={busy} onClick={() => saveEdit(hearing)}>
                      Save and confirm
                    </button>
                    <button
                      type="button"
                      className="cf-btn cf-btn--flush"
                      disabled={busy}
                      onClick={() => {
                        setEditingId(null);
                        setForm(null);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="hearing-actions review-row-actions">
                  <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={() => void resolve(hearing, "confirm")}>
                    Confirm
                  </button>
                  <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => startEdit(hearing)}>
                    Edit then confirm
                  </button>
                  <button type="button" className="cf-btn cf-btn--flush" disabled={busy} onClick={() => confirmDismiss(hearing)}>
                    Dismiss
                  </button>
                  <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => onOpen(hearing)}>
                    Details
                  </button>
                </div>
              )}
              {rowError && rowError.id === hearing.hearing_id && (
                <p className="hearing-form-error" role="alert">
                  {rowError.message}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
