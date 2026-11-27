"use client";

import { useEffect, useState } from "react";
import { openClientInNewTab } from "@/lib/clientLink";
import type { DuplicatePair } from "@/lib/duplicates";

export function DuplicatesList() {
  const [items, setItems] = useState<DuplicatePair[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/clients/duplicates")
      .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
      .then(({ ok, body }) => {
        if (cancelled) return;
        if (!ok) setError(String(body.error ?? "Duplicate clients could not be loaded."));
        else setItems((body.items ?? []) as DuplicatePair[]);
      })
      .catch(() => !cancelled && setError("Duplicate clients could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="duplicates-list">
      {error && <p className="new-client-error" role="alert">{error}</p>}
      {items && items.length === 0 && <p>No likely duplicates among the open clients.</p>}
      {items && items.length > 0 && (
        <>
          <p className="new-client-note">
            {items.length} likely {items.length === 1 ? "pair" : "pairs"}. Open a client to check it and merge from there.
          </p>
          <table className="removed-page-table">
            <thead>
              <tr>
                <th>Client</th>
                <th>Looks like</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {items.map((pair) => (
                <tr key={`${pair.a.matter_id}-${pair.b.matter_id}`}>
                  <td>
                    <button type="button" className="cf-btn cf-btn--flush" onClick={() => openClientInNewTab(pair.a.client_name, { matterId: pair.a.matter_id })}>
                      {pair.a.client_name}
                    </button>
                  </td>
                  <td>
                    <button type="button" className="cf-btn cf-btn--flush" onClick={() => openClientInNewTab(pair.b.client_name, { matterId: pair.b.matter_id })}>
                      {pair.b.client_name}
                    </button>
                  </td>
                  <td>{pair.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
