"use client";

import { useState } from "react";
import { BoardConfirm } from "./BoardConfirm";
import { NUDGE_FAILED_LINE, NUDGE_NOTE, nudgeLabel, nudgeQuestion } from "@/lib/nudge";
import type { NudgeDoc } from "@/lib/nudge";

export function NudgeCell({ matterId, clientName, doc, className, onChanged }: { matterId: string; clientName: string; doc: NudgeDoc; className: string; onChanged?: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function yes() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/nudge", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ matter_id: matterId, doc }) });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(String(body.error ?? NUDGE_FAILED_LINE));
        return;
      }
      setOpen(false);
      setDone(true);
      onChanged?.();
    } catch {
      setError(NUDGE_FAILED_LINE);
    } finally {
      setBusy(false);
    }
  }

  if (done) return <td className={className}>Nudged</td>;
  return (
    <td className={className}>
      <button type="button" className="sb-wetransfer sb-nudge" aria-haspopup="dialog" aria-label={nudgeLabel(clientName, doc)} onClick={() => setOpen(true)}>
        Nudge
      </button>
      {open && (
        <BoardConfirm
          titleId={`nudge-title-${matterId}-${doc}`}
          title={nudgeQuestion(clientName)}
          detail={NUDGE_NOTE}
          yesLabel="OK"
          noLabel="Cancel"
          error={error}
          busy={busy}
          onYes={yes}
          onNo={() => {
            if (!busy) {
              setOpen(false);
              setError("");
            }
          }}
        />
      )}
    </td>
  );
}
