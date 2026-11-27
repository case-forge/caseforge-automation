"use client";

import { useCallback, useEffect, useState } from "react";
import { formatDateForDisplay } from "@/lib/types";
import { isMergeRow, removedStateLabel, undoActionFor, undoExplanation, type RemovedClient } from "@/lib/removedClients";

export type RemovedShow = "all" | "removed" | "merged";

const EMPTY: Record<RemovedShow, string> = {
  all: "No client has been removed or merged.",
  removed: "No client has been removed.",
  merged: "No client has been merged.",
};

export function RemovedClientsTable({ show = "all", onChanged }: { show?: RemovedShow; onChanged?: () => void }) {
  const [items, setItems] = useState<RemovedClient[] | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [asking, setAsking] = useState("");

  const load = useCallback(
    () =>
      fetch("/api/clients/removed")
        .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
        .then(({ ok, body }) => {
          if (!ok) {
            setError(String(body.error ?? "Removed clients could not be loaded."));
            return;
          }
          setItems((body.items ?? []) as RemovedClient[]);
        })
        .catch(() => setError("Removed clients could not be loaded.")),
    [],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function undo(row: RemovedClient) {
    if (busy) return;
    setBusy(row.matter_id);
    setAsking("");
    setNote([]);
    try {
      const res = await fetch("/api/clients/removed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: undoActionFor(row), matter_id: row.matter_id }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setNote([String(body.error ?? "The change could not be undone.")]);
      } else {
        setNote(["The client is back.", ...((body.cannot_restore ?? []) as string[])]);
      }
      await load();
      onChanged?.();
    } finally {
      setBusy("");
    }
  }

  const rows = (items ?? []).filter((row) => (show === "all" ? true : show === "merged" ? isMergeRow(row) : !isMergeRow(row)));

  return (
    <div className="removed-list">
      {note.length > 0 && (
        <ul className="removed-page-note" role="status">
          {note.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {error && <p className="new-client-error" role="alert">{error}</p>}
      {items && rows.length === 0 && <p>{EMPTY[show]}</p>}
      {rows.length > 0 && (
        <>
          <p className="new-client-note">Newest first. {rows.length} {rows.length === 1 ? "row" : "rows"}.</p>
          <table className="removed-page-table">
            <thead>
              <tr>
                <th>Client</th>
                <th>{show === "merged" ? "Merged" : "Removed"}</th>
                <th>Reason</th>
                <th>State</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const key = `${row.matter_id}-${row.removed_utc}`;
                return (
                  <tr key={key}>
                    <td>
                      {row.client_name}
                    </td>
                    <td>
                      {formatDateForDisplay(row.removed_utc)} by {row.removed_by}
                    </td>
                    <td>{row.reason}</td>
                    <td>
                      {removedStateLabel(row)}
                      {row.purge_note && <div className="new-client-note">{row.purge_note}</div>}
                    </td>
                    <td>
                      {row.can_undo && asking !== key && (
                        <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy !== ""} onClick={() => setAsking(key)}>
                          Undo
                        </button>
                      )}
                      {row.can_undo && asking === key && (
                        <div className="removed-undo-ask" role="group" aria-label="Confirm undo">
                          <p>{undoExplanation(row)}</p>
                          <button type="button" className="cf-btn cf-btn--primary cf-btn--small" disabled={busy !== ""} onClick={() => void undo(row)} autoFocus>
                            {busy === row.matter_id ? "Undoing…" : "Undo it"}
                          </button>
                          <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy !== ""} onClick={() => setAsking("")}>
                            Keep it
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
