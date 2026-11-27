"use client";

import { useState } from "react";

export function RemoveBillingButton({ draftId, onRemoved }: { draftId: string; onRemoved: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/attendance-notes/delete-billing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft_id: draftId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || "Could not remove the charge.");
      setAsking(false);
      onRemoved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the charge.");
    } finally {
      setBusy(false);
    }
  }

  if (!asking) {
    return (
      <button type="button" className="cf-btn cf-btn--flush cf-btn--small cf-btn--danger no-print" onClick={() => setAsking(true)}>
        Remove from bill
      </button>
    );
  }
  return (
    <span className="remove-billing no-print" role="group" aria-label="Confirm removing this charge">
      <span>Take this charge off the bill? The note stays in SharePoint, and Undo under Removed puts it back.</span>
      <button type="button" className="cf-btn cf-btn--flush cf-btn--small cf-btn--danger" disabled={busy} onClick={() => void remove()}>
        {busy ? "Removing..." : "Yes, remove it"}
      </button>
      <button type="button" className="cf-btn cf-btn--flush cf-btn--small" disabled={busy} onClick={() => setAsking(false)}>
        Keep it
      </button>
      {error && (
        <span className="an-form-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}
