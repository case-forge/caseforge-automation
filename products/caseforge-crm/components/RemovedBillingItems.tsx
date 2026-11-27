"use client";

import { useState } from "react";
import type { BillOfCostsRemovedItem } from "@/lib/types";
import { formatDateForDisplay } from "@/lib/types";

export function RemovedBillingItems({ items, onRestored }: { items: BillOfCostsRemovedItem[]; onRestored: () => void }) {

  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  if (items.length === 0) return null;

  async function undo(itemId: string) {
    setBusy(itemId);
    setError("");
    try {
      const res = await fetch("/api/billing/restore-item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_id: itemId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || "Could not put the charge back.");
      onRestored();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not put the charge back.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="billing-removed no-print">
      <button
        type="button"
        className="cf-btn cf-btn--flush cf-btn--small"
        aria-expanded={expanded}
        aria-controls="billing-removed-list"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "Hide removed" : `Removed (${items.length})`}
      </button>
      {expanded && (
        <ul id="billing-removed-list" className="billing-removed-list" aria-label="Charges taken off the bill">
          {items.map((item) => (
            <li key={item.item_id} className="billing-removed-item">
              <span className="billing-removed-text">
                <span>
                  {item.item_date} {item.description}
                </span>
                <span className="billing-removed-meta">
                  {item.category_label}, £{item.net_amount} + VAT £{item.vat_amount}. Removed
                  {item.removed_by ? ` by ${item.removed_by}` : ""} on {formatDateForDisplay(item.removed_utc)}
                </span>
              </span>
              <button
                type="button"
                className="cf-btn cf-btn--flush cf-btn--small"
                disabled={busy !== ""}
                onClick={() => void undo(item.item_id)}
                aria-label={`Undo: put ${item.description} back on the bill`}
              >
                {busy === item.item_id ? "Putting back..." : "Undo"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {error && (
        <span className="an-form-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
