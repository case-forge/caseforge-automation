"use client";

import { listHref } from "@/lib/clientLists";
import Link from "next/link";
import { useState } from "react";
import { useModalFocus } from "@/lib/modalFocus";
import { removeConfirmed } from "@/lib/removedClients";
import { DialogClose } from "./DialogClose";

type Result = { done?: string[]; not_done?: string[] };

export function RemoveClientButton({ matterId, clientName }: { matterId: string; clientName: string }) {
  const [open, setOpen] = useState(false);
  const dialogRef = useModalFocus<HTMLDivElement>(open);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);

  function openDialog() {
    setOpen(true);
  }

  function close() {
    if (result) {
      window.location.reload();
      return;
    }
    setOpen(false);
    setTyped("");
    setReason("");
    setError("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/clients/removed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "remove", matter_id: matterId, typed_name: typed, reason }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(String(body.error ?? "The client could not be removed."));
        return;
      }
      setResult(body as Result);
    } catch {
      setError("The client could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  const ready = removeConfirmed(typed, clientName) && reason.trim().length >= 3;

  return (
    <>
      <button type="button" className="cf-btn cf-btn--neutral cf-btn--danger" aria-haspopup="dialog" onClick={openDialog}>
        Remove client
      </button>
      {open && (
        <div className="new-client-backdrop" role="presentation">
          <div
            ref={dialogRef}
            className="new-client-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="remove-client-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
          >
            <DialogClose onClose={close} />
            <h2 id="remove-client-title">Remove {clientName}</h2>
            {result ? (
              <div className="new-client-done" role="status">
                <p>The client is removed and hidden. Undo is on the Removed clients page for 30 days.</p>
                <ul>
                  {(result.done ?? []).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                  {(result.not_done ?? []).map((line) => (
                    <li key={line} className="new-client-error">{line}</li>
                  ))}
                </ul>
                <div className="new-client-actions">
                  <Link href={listHref("removed")}>Removed clients</Link>
                  <button type="button" className="cf-btn cf-btn--primary" onClick={close}>Done</button>
                </div>
              </div>
            ) : (
              <form onSubmit={submit}>
                <p className="new-client-note">
                  The client is hidden everywhere and the folder is moved to 000 Removed in the same book. Unsent
                  Documenso envelopes are voided and unsent drafts go to Deleted Items. Nothing is deleted; a real
                  client is never purged.
                </p>
                <label>
                  Type the client&apos;s name to confirm
                  <input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" placeholder={clientName} />
                </label>
                <label>
                  Reason
                  <input value={reason} onChange={(e) => setReason(e.target.value)} autoComplete="off" />
                </label>
                {error && <p className="new-client-error" role="alert">{error}</p>}
                <div className="new-client-actions">
                  <Link href={listHref("removed")}>Removed clients</Link>
                  <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={close}>Cancel</button>
                  <button type="submit" className="cf-btn cf-btn--primary cf-btn--danger" disabled={!ready || busy}>{busy ? "Removing…" : "Remove"}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
