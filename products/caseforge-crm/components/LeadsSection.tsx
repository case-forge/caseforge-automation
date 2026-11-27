"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { filterLeads, safeHttpsUrl, truncateText } from "@/lib/hearings";
import type { HearingLead } from "@/lib/hearings";
import { fetchLeads, isAbort, resolveLead } from "@/lib/hearingsClient";
import { IconAlert } from "./icons";

function receivedLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "date unknown" : date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function LeadsSection({
  refreshKey,
  onChanged,
  onAddHearing,
  filter = "",
}: {
  refreshKey: number;

  filter?: string;

  onChanged: () => void;

  onAddHearing: (lead: HearingLead) => void;
}) {
  const [leads, setLeads] = useState<HearingLead[] | null>(null);
  const shownLeads = leads ? filterLeads(leads, filter) : null;
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    fetchLeads(controller.signal)
      .then((body) => setLeads(body.leads))
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setLoadError(err instanceof Error ? err.message : "Could not load the emails to check");
      });
    return () => controller.abort();
  }, [refreshKey]);

  function focusRow(id: number | undefined) {
    if (id === undefined) return;
    window.setTimeout(() => {
      listRef.current?.querySelector<HTMLElement>(`[data-lead-id="${id}"]`)?.focus();
    }, 0);
  }

  async function close(lead: HearingLead, action: "done" | "dismissed") {
    if (action === "dismissed" && !window.confirm("Mark this email as not a hearing? It leaves the list; a record of it is kept.")) return;
    setBusyId(lead.lead_id);
    setRowError(null);
    try {
      await resolveLead(lead.lead_id, action);
      const list = leads ?? [];
      const index = list.findIndex((l) => l.lead_id === lead.lead_id);
      const next = list[index + 1] ?? list[index - 1];
      setLeads(list.filter((l) => l.lead_id !== lead.lead_id));
      onChanged();
      focusRow(next?.lead_id);
    } catch (err) {
      setRowError({ id: lead.lead_id, message: err instanceof Error ? err.message : "Could not save that" });
    } finally {
      setBusyId(null);
    }
  }

  function openEmail(lead: HearingLead) {
    const link = safeHttpsUrl(lead.source_web_link);
    if (link) window.open(link, "_blank", "noopener,noreferrer");
  }

  function onKeyDown(e: KeyboardEvent<HTMLUListElement>) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const target = e.target as HTMLElement;
    if (target.closest("input, textarea, select, a")) return;
    const row = target.closest<HTMLElement>("[data-lead-id]");
    if (!row || !shownLeads || busyId !== null) return;
    const id = Number(row.dataset.leadId);
    const index = shownLeads.findIndex((l) => l.lead_id === id);
    const lead = shownLeads[index];
    if (!lead) return;

    switch (e.key) {
      case "ArrowDown":
      case "j":
        e.preventDefault();
        focusRow(shownLeads[index + 1]?.lead_id);
        break;
      case "ArrowUp":
      case "k":
        e.preventDefault();
        focusRow(shownLeads[index - 1]?.lead_id);
        break;
      case "a":
        e.preventDefault();
        onAddHearing(lead);
        break;
      case "d":
        e.preventDefault();
        void close(lead, "done");
        break;
      case "n":
        e.preventDefault();
        void close(lead, "dismissed");
        break;
      case "o":
        e.preventDefault();
        openEmail(lead);
        break;
    }
  }

  return (
    <section className="review-queue leads-section" aria-label="Emails to check">
      <h3 className="review-section-title">Emails to check</h3>
      {loadError ? (
        <p className="hearing-form-error" role="alert">
          {loadError}
        </p>
      ) : leads === null ? (
        <p className="hearing-muted">Loading the emails to check...</p>
      ) : leads.length === 0 ? (
        <p className="hearing-muted">No emails to check. Every hearing-like email has been read into a hearing or dealt with.</p>
      ) : (
        <>
          <p className="hearing-muted review-queue-hint">
            {filter.trim() ? `${shownLeads?.length ?? 0} of ${leads.length}` : leads.length} {leads.length === 1 ? "email looks" : "emails look"} like a hearing notice but could not be read into a hearing. Keys: j and k move, a
            adds a hearing, d marks done, n says not a hearing, o opens the email.
          </p>
          <ul className="review-list" ref={listRef} onKeyDown={onKeyDown}>
            {(shownLeads ?? []).map((lead) => {
              const link = safeHttpsUrl(lead.source_web_link);
              const subject = lead.source_subject.trim() || "(no subject)";
              const busy = busyId === lead.lead_id;
              return (
                <li
                  key={lead.lead_id}
                  className="review-row lead-row"
                  data-lead-id={lead.lead_id}
                  tabIndex={0}
                  aria-label={`Email to check: ${truncateText(subject, 120)}, received ${receivedLabel(lead.source_received_utc)}`}
                  aria-busy={busy || undefined}
                >
                  <div className="review-row-main">
                    <div className="review-row-title">
                      <strong className="lead-subject" title={subject}>
                        {truncateText(subject)}
                      </strong>
                      <span>Received {receivedLabel(lead.source_received_utc)}</span>
                    </div>
                    <p className="review-row-reason">
                      <IconAlert className="review-row-reason-icon" aria-hidden="true" />
                      <span>{lead.reason || "This email could not be read into a hearing."}</span>
                    </p>
                  </div>
                  <div className="hearing-actions review-row-actions">
                    <button type="button" className="cf-btn cf-btn--secondary" disabled={busy} onClick={() => onAddHearing(lead)}>
                      Add hearing
                    </button>
                    <button type="button" className="cf-btn cf-btn--flush" disabled={busy} onClick={() => void close(lead, "dismissed")}>
                      Not a hearing
                    </button>
                    <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={() => void close(lead, "done")}>
                      Done
                    </button>
                    {link ? (
                      <a className="cf-btn cf-btn--neutral lead-open" href={link} target="_blank" rel="noopener noreferrer">
                        Open email
                      </a>
                    ) : (
                      <span className="hearing-muted lead-nolink">No link to the email</span>
                    )}
                  </div>
                  {rowError && rowError.id === lead.lead_id && (
                    <p className="hearing-form-error" role="alert">
                      {rowError.message}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
