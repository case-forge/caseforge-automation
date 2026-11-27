"use client";

import { useEffect, useState } from "react";
import { useModalFocus } from "@/lib/modalFocus";
import { ageLabel } from "@/lib/robotNotices";
import { DialogClose } from "./DialogClose";
import {
  cancelPendingNewClient,
  emailStateLabel,
  fetchPendingNewClients,
  formsBackLabel,
  isUnfinished,
  resumedLines,
  resumePendingNewClient,
  unfinishedLabel,
  waitedLabel,
  waitLine,
  waitTone,
  type PendingNewClientsList,
} from "@/lib/pendingNewClients";

export function PendingNewClients({ onClose }: { onClose: () => void }) {
  const dialogRef = useModalFocus<HTMLDivElement>(true);
  const [list, setList] = useState<PendingNewClientsList | null>(null);
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [finished, setFinished] = useState<{ id: number; lines: string[] } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPendingNewClients()
      .then((body) => {
        if (!cancelled) setList(body);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "The list could not be read.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function cancel(pendingId: number) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      setList(await cancelPendingNewClient(pendingId));
      setConfirming(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The new client could not be cancelled.");
    } finally {
      setBusy(false);
    }
  }

  async function finish(pendingId: number) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const made = await resumePendingNewClient(pendingId);
      setFinished({ id: pendingId, lines: resumedLines(made) });
      setList(await fetchPendingNewClients());
    } catch (err) {
      setError(err instanceof Error ? err.message : "The new client could not be finished. Nothing was made twice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="new-client-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="new-client-dialog pending-clients-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pending-clients-title"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <DialogClose onClose={onClose} />
        <h2 id="pending-clients-title">Waiting for their New Client Form</h2>
        <p className="new-client-note">
          Each client is added to the CRM when their signed New Client Form comes back. The number on the button counts the ones whose
          email has not been sent yet.
        </p>
        {error && <p className="new-client-error" role="alert">{error}</p>}
        {!list && !error && <p className="new-client-note">Loading…</p>}
        {list && list.items.length === 0 && <p className="pending-clients-empty">No new client is waiting for their forms.</p>}
        {list && list.items.length > 0 && (
          <ul className="pending-clients-list">
            {list.items.map((item) => (
              <li key={item.pending_id} className="pending-clients-item" data-email={item.email_state} data-wait={waitTone(item)}>
                <div className="pending-clients-head">
                  <span className="pending-clients-name">{item.full_name}</span>
                  <span className="pending-clients-when">
                    {ageLabel(item.created_utc)}
                    {waitTone(item) !== "normal" && `, waiting ${waitedLabel(item.waiting_minutes ?? 0)}`}
                  </span>
                </div>
                {waitLine(item) && (
                  <p className="pending-clients-wait" role={waitTone(item) === "overdue" ? "alert" : undefined}>
                    {waitLine(item)}
                  </p>
                )}
                <dl className="pending-clients-facts">
                  <dt>Email</dt>
                  <dd className="pending-clients-email">{item.email}</dd>
                  {item.phone && (
                    <>
                      <dt>Telephone</dt>
                      <dd>
                        <a href={`tel:${item.phone.replace(/[^+\d]/g, "")}`}>{item.phone}</a>
                      </dd>
                    </>
                  )}
                  <dt>Made by</dt>
                  <dd>
                    {item.created_by}, {item.category_label}
                  </dd>
                  <dt>Email sent?</dt>
                  <dd data-state={item.email_state}>{emailStateLabel(item.email_state)}</dd>
                  <dt>Forms back</dt>
                  <dd>{formsBackLabel(item.forms_back)}</dd>
                </dl>
                {isUnfinished(item) && <p className="pending-clients-unfinished">{unfinishedLabel(item.stage)}</p>}
                {item.note && <p className="new-client-note">{item.note}</p>}
                {finished?.id === item.pending_id && (
                  <div className="new-client-resumed" role="status">
                    {finished.lines.map((line) => (
                      <p key={line}>{line}</p>
                    ))}
                  </div>
                )}
                {confirming === item.pending_id ? (
                  <div className="pending-clients-confirm" role="group" aria-label={`Cancel ${item.full_name}`}>
                    <p>
                      Take {item.full_name} off this list? The folder, the draft in Outlook and the signing links stay as they are; a
                      form signed later is held for a person and nothing is made.
                    </p>
                    <div className="new-client-actions">
                      <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={() => setConfirming(null)}>Keep</button>
                      <button type="button" className="cf-btn cf-btn--primary cf-btn--danger pending-clients-cancel-yes" disabled={busy} onClick={() => void cancel(item.pending_id)}>
                        {busy ? "Working…" : "Cancel this client"}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="new-client-actions">
                    {item.draft_web_link && item.email_state !== "sent" && (
                      <a href={item.draft_web_link} target="_blank" rel="noreferrer">
                        Open the draft
                      </a>
                    )}
                    {isUnfinished(item) && (
                      <button type="button" className="cf-btn cf-btn--primary pending-clients-finish" disabled={busy} onClick={() => void finish(item.pending_id)}>
                        {busy ? "Working…" : "Finish"}
                      </button>
                    )}
                    <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={() => setConfirming(item.pending_id)}>Cancel</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="new-client-actions">
          <button type="button" className="cf-btn cf-btn--primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
