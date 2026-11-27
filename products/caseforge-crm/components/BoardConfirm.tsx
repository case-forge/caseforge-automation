"use client";

import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { useModalFocus } from "@/lib/modalFocus";

export function BoardConfirm({
  titleId,
  title,
  detail,
  error,
  busy,
  onYes,
  onNo,
  className = "",
  yesDisabled = false,
  yesLabel = "Yes",
  noLabel = "No",
  children,
}: {
  titleId: string;
  title: ReactNode;

  detail?: ReactNode;
  error?: string;
  busy: boolean;
  onYes: () => void;
  onNo: () => void;
  className?: string;

  yesDisabled?: boolean;

  yesLabel?: string;
  noLabel?: string;

  children?: ReactNode;
}) {
  const dialogRef = useModalFocus<HTMLDivElement>(true);
  return createPortal(
    <div className="new-client-backdrop" role="presentation" onClick={onNo}>
      <div
        ref={dialogRef}
        className={`new-client-dialog sb-wetransfer-dialog ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.stopPropagation();
            onNo();
          }
        }}
      >
        <h2 id={titleId}>{title}</h2>
        {detail && <p className="sb-confirm-detail">{detail}</p>}
        {children}
        {error && (
          <p className="sb-wetransfer-error" role="alert">
            {error}
          </p>
        )}
        <div className="sb-wetransfer-actions">
          <button type="button" className="cf-btn cf-btn--primary" disabled={busy || yesDisabled} aria-busy={busy} onClick={onYes}>
            {busy ? "Saving…" : yesLabel}
          </button>
          <button
            type="button"
            className="cf-btn cf-btn--secondary"
            disabled={busy}
            onClick={(event) => {
              event.stopPropagation();
              onNo();
            }}
          >
            {noLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
