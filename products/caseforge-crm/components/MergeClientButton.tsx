"use client";

import { listHref } from "@/lib/clientLists";
import Link from "next/link";
import { useState } from "react";
import { useModalFocus } from "@/lib/modalFocus";
import { DialogClose } from "./DialogClose";
import {
  detailRows,
  removeConfirmed,
  mergeConfirmed,
  mergeMoveLines,
  picksBody,
  type MergePicks,
  type MergePreview,
} from "@/lib/removedClients";

export function MergeClientButton({ matterId: openedFrom }: { matterId: string }) {

  const [matterId, setMatterId] = useState(openedFrom);
  const [open, setOpen] = useState(false);
  const dialogRef = useModalFocus<HTMLDivElement>(open);

  const [other, setOther] = useState("");
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [typedFrom, setTypedFrom] = useState("");
  const [typedInto, setTypedInto] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [merged, setMerged] = useState(false);
  const [picks, setPicks] = useState<MergePicks>({});

  function openDialog() {
    setOpen(true);
  }

  function swap() {
    if (!preview || busy) return;
    const keep = preview.from.matter_id;
    const away = preview.into.matter_id;
    setMatterId(keep);
    setOther(away);
    setTypedFrom("");
    setTypedInto("");
    void loadPreview(keep, away);
  }

  function close() {
    if (merged) {
      window.location.reload();
      return;
    }
    setOpen(false);
    setMatterId(openedFrom);
    setOther("");
    setPreview(null);
    setPicks({});
    setTypedFrom("");
    setTypedInto("");
    setReason("");
    setError("");
  }

  async function loadPreview(keepId = matterId, awayId = other.trim()) {
    if (busy || !/^\d+$/.test(awayId)) return;
    setBusy(true);
    setError("");
    setPreview(null);
    setPicks({});
    try {
      const res = await fetch(`/api/clients/merge?from=${encodeURIComponent(awayId)}&into=${encodeURIComponent(keepId)}`);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) setError(String(body.error ?? "The preview could not be made."));
      else setPreview(body as MergePreview);
    } catch {
      setError("The preview could not be made.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !preview) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/clients/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_matter_id: preview.from.matter_id,
          into_matter_id: preview.into.matter_id,
          typed_from: typedFrom,
          typed_into: typedInto,
          reason,
          choices: picksBody(preview, picks),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) setError(String(body.error ?? "The clients could not be merged."));
      else setMerged(true);
    } catch {
      setError("The clients could not be merged.");
    } finally {
      setBusy(false);
    }
  }

  const ready = mergeConfirmed(preview, typedFrom, typedInto) && reason.trim().length >= 3;

  const missing: string[] = [];
  if (preview && preview.refusals.length === 0) {
    if (!removeConfirmed(typedFrom, preview.from.client_name ?? "")) missing.push(`type "${preview.from.client_name}" exactly in the first name box`);
    if (!removeConfirmed(typedInto, preview.into.client_name ?? "")) missing.push(`type "${preview.into.client_name}" exactly in the second name box`);
    if (reason.trim().length < 3) missing.push("give a reason");
  }

  return (
    <>
      <button type="button" className="cf-btn cf-btn--neutral" aria-haspopup="dialog" onClick={openDialog}>
        Merge client
      </button>
      {open && (
        <div className="new-client-backdrop" role="presentation">
          <div
            ref={dialogRef}
            className={`new-client-dialog merge-dialog${preview && !merged ? " merge-dialog--wide" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="merge-client-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
          >
            {!merged && <DialogClose onClose={close} />}
            <h2 id="merge-client-title">Merge another client into this one</h2>
            {merged ? (
              <div className="new-client-done">
                <p>
                  Matter {preview?.from.matter_id} is merged into matter {preview?.into.matter_id} and is now hidden. Undo is on
                  the Removed and merged clients page for 30 days.
                </p>
                <div className="new-client-actions">
                  <Link href={listHref("removed")} target="_blank" rel="noopener noreferrer" className="cf-btn cf-btn--secondary">Removed and merged clients</Link>
                  <button type="button" className="cf-btn cf-btn--primary" onClick={close}>Done</button>
                </div>
              </div>
            ) : (
              <form onSubmit={submit}>
                <label>
                  Merge matter number
                  <input value={other} onChange={(e) => {
                      setOther(e.target.value);
                      setPreview(null);
                    }} inputMode="numeric" autoComplete="off" />
                  into this client (matter {matterId}), which is the one kept
                </label>
                <div className="new-client-actions">
                  {preview && (
                    <button type="button" className="cf-btn cf-btn--neutral" disabled={busy} onClick={swap}>
                      Swap: keep matter {preview.from.matter_id} instead
                    </button>
                  )}
                  <button type="button" className="cf-btn cf-btn--primary" disabled={busy || !/^\d+$/.test(other.trim())} onClick={() => void loadPreview()}>
                    Preview
                  </button>
                </div>
                {preview && (
                  <div className="new-client-preview" aria-live="polite">
                    <p className="new-client-preview-head">
                      Preview, nothing moved yet: {preview.from.client_name ?? preview.from.matter_id} (matter {preview.from.matter_id})
                      is merged into {preview.into.client_name ?? preview.into.matter_id} (matter {preview.into.matter_id}), which is kept
                    </p>
                    {preview.refusals.length > 0 && (
                      <ul role="alert">
                        {preview.refusals.map((line) => (
                          <li key={line} className="new-client-error">{line}</li>
                        ))}
                      </ul>
                    )}
                    <ul>
                      {mergeMoveLines(preview).map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                      {preview.folder.note && <li>{preview.folder.note}</li>}
                    </ul>
                  </div>
                )}
                {preview && preview.refusals.length === 0 && detailRows(preview, picks).length > 0 && (
                  <div className="merge-changes" aria-live="polite">
                    <p className="new-client-preview-head">
                      Details on matter {preview.into.matter_id} ({preview.into.client_name ?? "the surviving client"}) before and after.
                      A blank is never written over a filled value.
                    </p>
                    <table>
                      <thead>
                        <tr>
                          <th>Detail</th>
                          <th>Matter {preview.into.matter_id} now</th>
                          <th>Matter {preview.from.matter_id} has</th>
                          <th>After merge</th>
                          <th title={`Overwrite with matter ${preview.from.matter_id}'s value`}>Use {preview.from.matter_id}&apos;s</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailRows(preview, picks).map((r) => (
                          <tr key={r.id} className={r.kind === "overwrite" ? "merge-overwrites" : undefined}>
                            <td>{r.label}</td>
                            <td>{r.b}</td>
                            <td>{r.a}</td>
                            <td>{r.after}{r.kind === "fill" ? " (filled)" : r.kind === "overwrite" ? " (overwritten)" : " (kept)"}</td>
                            <td>
                              {r.kind === "fill" ? null : (
                                <input
                                  type="checkbox"
                                  aria-label={`Overwrite ${r.label} with matter ${preview.from.matter_id}'s`}
                                  checked={r.kind === "overwrite"}
                                  onChange={(e) => setPicks((p) => ({ ...p, [r.id]: e.target.checked ? "a" : "b" }))}
                                />
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {preview && preview.refusals.length === 0 && preview.choices?.second_applicants.length ? (
                  <fieldset className="merge-conflicts">
                    <legend>Second applicant</legend>
                    {preview.choices.second_applicants.map((s) => (
                      <fieldset key={s.id} className="merge-conflict">
                        <legend>Second applicant row</legend>
                        <p>
                          Matter {preview.into.matter_id} already has an applicant ({s.b_name}, born {s.b_dob || "not recorded"}). Matter {preview.from.matter_id} also has one ({s.name}, born {s.dob || "not recorded"}).
                        </p>
                        <label>
                          <input type="radio" name={s.id} checked={picks[s.id] === "keep"} onChange={() => setPicks((p) => ({ ...p, [s.id]: "keep" }))} />
                          Keep matter {preview.from.matter_id}&apos;s row (matter {preview.into.matter_id} ends up with both)
                        </label>
                        <label>
                          <input type="radio" name={s.id} checked={picks[s.id] !== "keep"} onChange={() => setPicks((p) => ({ ...p, [s.id]: "discard" }))} />
                          Discard matter {preview.from.matter_id}&apos;s row (it stays on matter {preview.from.matter_id})
                        </label>
                      </fieldset>
                    ))}
                  </fieldset>
                ) : null}
                {preview && preview.refusals.length === 0 && (
                  <>
                    <label>
                      Type the name of the client merged away (matter {preview.from.matter_id})
                      <input value={typedFrom} onChange={(e) => setTypedFrom(e.target.value)} autoComplete="off" placeholder={preview.from.client_name} />
                    </label>
                    <label>
                      Type the name of the client kept (matter {preview.into.matter_id})
                      <input value={typedInto} onChange={(e) => setTypedInto(e.target.value)} autoComplete="off" placeholder={preview.into.client_name} />
                    </label>
                    <label>
                      Reason
                      <input value={reason} onChange={(e) => setReason(e.target.value)} autoComplete="off" />
                    </label>
                  </>
                )}
                {missing.length > 0 && <p className="new-client-hint">To enable Merge: {missing.join("; ")}.</p>}
                {error && <p className="new-client-error" role="alert">{error}</p>}
                <div className="new-client-actions">
                  <button type="button" className="cf-btn cf-btn--flush dialog-button--quiet" onClick={close}>Cancel</button>
                  <button type="submit" className="cf-btn cf-btn--primary" disabled={!ready || busy}>{busy ? "Working…" : "Merge"}</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
