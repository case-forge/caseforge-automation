"use client";

import { useState } from "react";
import { ambiguityNote, bestGuess, confidenceLabel, confirmBlockedReason, confirmCopiesWarning, confirmScan, kindLabel, MAX_COPIES, parseCopies } from "@/lib/scanResolver";
import type { ScanCandidates } from "@/lib/scanResolver";

export function ScanConfirm({ scan, onFiled, onlyMatterId }: { scan: ScanCandidates; onFiled?: () => void; onlyMatterId?: string }) {
  const candidates = onlyMatterId ? scan.candidates.filter((c) => c.matter_id === onlyMatterId) : scan.candidates;
  const best = candidates[0] ?? bestGuess(scan);
  const [picked, setPicked] = useState("");
  const [copies, setCopies] = useState("1");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string } | null>(null);
  const [filed, setFiled] = useState(false);

  const matterId = picked || (best?.matter_id ?? "");
  const chosen = candidates.find((c) => c.matter_id === matterId) ?? best;
  const blocked = confirmBlockedReason(matterId, copies, busy);
  const warning = confirmCopiesWarning(copies);
  const kind = kindLabel(scan.kind);

  async function press() {
    if (!matterId) return;
    setBusy(true);
    try {
      const count = parseCopies(copies);
      let out = await confirmScan(scan.id, matterId, count, scan.kind);

      if (out.case_flow?.needs_confirm && window.confirm(`${out.case_flow.message}\n\nTell Case flow about this order as well?`)) {
        out = await confirmScan(scan.id, matterId, count, scan.kind, true);
      }
      setOutcome({ ok: true, message: out.message });
      setFiled(true);
      onFiled?.();
    } catch (err) {
      setOutcome({ ok: false, message: err instanceof Error ? err.message : "The scan was not filed." });
    } finally {
      setBusy(false);
    }
  }

  if (filed) {
    return outcome ? <p className="cf2-note" role="status">{outcome.message}</p> : null;
  }

  return (
    <div className="scan-confirm">
      {!chosen ? (
        <p className="cf2-note">{scan.text_read ? "No client could be estimated from the file name or the text." : "No client could be estimated from the file name, and the text could not be read."}</p>
      ) : (
        <>
          <p className="scan-confirm-guess">
            <strong>{chosen.client_name}</strong> <span className="scan-confidence">Confidence {confidenceLabel(chosen)}</span>
            {chosen.closed && <span className="vscan-tag">Closed matter</span>}
          </p>
          {ambiguityNote(chosen) && <p className="cf2-error" role="alert">{ambiguityNote(chosen)}</p>}
          <details>
            <summary>Why this client</summary>
            <ul className="vscan-hints">
              {chosen.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </details>
          {candidates.length > 1 && (
            <label className="vscan-date">
              Or pick another client
              <select value={matterId} onChange={(e) => setPicked(e.target.value)} disabled={busy}>
                {candidates.map((c) => (
                  <option key={c.matter_id} value={c.matter_id}>{c.client_name}: {confidenceLabel(c)}</option>
                ))}
              </select>
            </label>
          )}
          {kind && <p className="cf2-note">{kind}.</p>}
          <div className="vscan-actions">
            <label className="vscan-date">
              Copies
              <input type="number" min={1} max={MAX_COPIES} step={1} value={copies} onChange={(e) => setCopies(e.target.value)} disabled={busy} />
            </label>
            <button type="button" className="cf-btn cf-btn--primary" disabled={Boolean(blocked)} title={blocked} onClick={() => void press()}>
              {busy ? "Filing..." : "Confirm"}
            </button>
          </div>
          {warning && <p className="cf2-error" role="alert">{warning}</p>}
          <p className="cf2-note">{scan.label} Confirming moves the file into the client&apos;s folder. It is not billed.</p>
        </>
      )}
      {outcome && !outcome.ok && <p className="cf2-error" role="alert">{outcome.message}</p>}
    </div>
  );
}
