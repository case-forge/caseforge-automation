"use client";

import { useState } from "react";
import { BoardConfirm } from "./BoardConfirm";
import { refreshStatusBoardRows, useStatusBoardRows } from "@/lib/statusBoardRows";
import {
  acceptAll,
  acceptPlan,
  allTicked,
  namesInWords,
  pendingWetransfers,
  postWetransferGate,
  tickedToSend,
  toggleTick,
  wetransferGiven,
  wetransferInFlight,
} from "@/lib/wetransferBanner";

export function WetransferBanner() {
  const rows = useStatusBoardRows();
  const [asking, setAsking] = useState(false);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const pending = pendingWetransfers(rows ?? [], wetransferGiven);
  if (pending.length === 0) return null;

  function open() {
    setTicked(allTicked(pending));
    setError("");
    setAsking(true);
  }

  function close() {
    if (running) return;
    setAsking(false);
    setError("");
  }

  async function yes() {
    if (running) return;
    const ids = acceptPlan(tickedToSend(pending, ticked), wetransferGiven, wetransferInFlight);
    if (ids.length === 0) return;
    setRunning(true);
    setError("");
    try {
      const result = await acceptAll(ids, postWetransferGate, wetransferGiven, wetransferInFlight);
      await refreshStatusBoardRows();
      if (result.failed.length > 0) {
        const names = pending.filter((p) => result.failed.includes(p.matterId)).map((p) => p.name);
        setError(`The permission could not be recorded for ${namesInWords(names)}. Press Yes to try again.`);
        setTicked(new Set(result.failed));
      } else setAsking(false);
    } finally {
      setRunning(false);
    }
  }

  const count = tickedToSend(pending, ticked).length;
  return (
    <div className="wetransfer-banner" role="region" aria-label="WeTransfer downloads waiting">
      <p className="wetransfer-banner-text">
        <strong>WeTransfer:</strong> permission to download is waiting for {namesInWords(pending.map((p) => p.name))}.
      </p>
      <button type="button" className="cf-btn cf-btn--small wetransfer-banner-accept" aria-haspopup="dialog" onClick={open}>
        Accept
      </button>
      {asking && (
        <BoardConfirm
          titleId="wetransfer-banner-title"
          title="Do you grant permission to download the documents from WeTransfer?"
          detail="Each client below has their own consent. Untick anyone who has not agreed: only the ticked clients are downloaded."
          error={error}
          busy={running}
          yesDisabled={count === 0}
          onYes={() => void yes()}
          onNo={close}
          className="wetransfer-banner-dialog"
        >
          <fieldset className="wetransfer-banner-clients" disabled={running}>
            <legend className="review-mail-sr">Clients</legend>
            {pending.map((p) => (
              <label key={p.matterId} className="wetransfer-banner-client">
                <input type="checkbox" checked={ticked.has(p.matterId)} onChange={() => setTicked((t) => toggleTick(t, p.matterId))} />
                {p.name}
              </label>
            ))}
          </fieldset>
        </BoardConfirm>
      )}
    </div>
  );
}
