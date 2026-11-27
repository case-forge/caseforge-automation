"use client";

import { useState } from "react";
import { BoardConfirm } from "./BoardConfirm";
import { NudgeCell } from "./NudgeCell";
import { clientHref } from "@/lib/clientLink";
import { nudgeDocFor } from "@/lib/nudge";
import { PortalCell } from "./PortalCell";
import { showsPortal } from "@/lib/portalCell";
import type { StatusBoardItem } from "@/lib/matterMilestones";
import { boardDate } from "@/lib/matterMilestones";
import { boardLinkFor } from "@/lib/boardLinks";
import { BoardDateLink } from "./BoardDateLink";
import { refreshStatusBoardRows } from "@/lib/statusBoardRows";
import { wetransferGiven, wetransferInFlight } from "@/lib/wetransferBanner";
import {
  COMPACT_COLUMNS,
  daysWaiting,
  formatBoardDay,
  isNewReferral,
  waitingLabel,
} from "@/lib/boardCompact";

export function WaitingTag({ days }: { days: number | null }) {
  return days === null ? null : <span className="sb-waiting-tag">{waitingLabel(days)}</span>;
}

function WetransferGate({
  matterId,
  onChanged,
}: {
  matterId: string;
  onChanged?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function close() {
    if (busy) return;
    setOpen(false);
    setError("");
  }

  async function yes() {
    if (busy) return;

    if (wetransferGiven.has(matterId) || wetransferInFlight.has(matterId)) {
      setOpen(false);
      onChanged?.();
      return;
    }
    setBusy(true);
    setError("");
    wetransferInFlight.add(matterId);
    try {
      const res = await fetch("/api/wetransfer-gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ matter_id: matterId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(String(body.error ?? "The permission could not be recorded."));
        return;
      }
      wetransferGiven.add(matterId);
      setOpen(false);
      onChanged?.();
      void refreshStatusBoardRows();
    } catch {
      setError("The permission could not be recorded.");
    } finally {
      wetransferInFlight.delete(matterId);
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="sb-wetransfer"
        aria-haspopup="dialog"
        aria-label="WeTransfer: download permission needed"
        onClick={() => setOpen(true)}
      >
        WeTransfer
      </button>
      {open && (
        <BoardConfirm
          titleId={`wetransfer-title-${matterId}`}
          title="Do you grant permission to download the documents from WeTransfer?"
          error={error}
          busy={busy}
          onYes={yes}
          onNo={close}
        />
      )}
    </>
  );
}

export function StatusBoardTable({
  items,
  now,
  onChanged,
}: {
  items: readonly StatusBoardItem[];
  now?: Date;
  onChanged?: () => void;
}) {
  return (
    <div className="sb-compact-scroll">
      <table className="sb-compact-table">
        <thead>
          <tr>
            <th scope="col">Client</th>
            {COMPACT_COLUMNS.map((c) => (
              <th key={c.key} scope="col">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.matter_id}>
              <th scope="row">
                <a className="sb-client-link" href={clientHref(item.client_name, { matterId: item.matter_id })}>{item.client_name}</a>
                {isNewReferral(item, now) && (
                  <span className="sb-compact-tag">New</span>
                )}
                <WaitingTag days={daysWaiting(item, now)} />
              </th>
              {COMPACT_COLUMNS.map((c) => {
                const iso = c.value(item);
                const label = formatBoardDay(iso);
                const nudgeDoc = nudgeDocFor(item, c.key, iso);
                if (nudgeDoc) {
                  return <NudgeCell key={c.key} matterId={item.matter_id} clientName={item.client_name} doc={nudgeDoc} className="sb-compact-empty" onChanged={onChanged} />;
                }
                if (showsPortal(item, c.key, iso)) {
                  return <PortalCell key={c.key} className="sb-compact-empty" />;
                }
                if (c.key === "contacted" && item.wetransfer_pending) {
                  return (
                    <td key={c.key} className="sb-compact-empty">
                      <WetransferGate
                        matterId={item.matter_id}
                        onChanged={onChanged}
                      />
                    </td>
                  );
                }
                return label ? (
                  <td
                    key={c.key}
                    className="sb-compact-done"
                    title={boardDate(iso)}
                    aria-label={boardDate(iso)}
                  >
                    <BoardDateLink href={boardLinkFor(item, c.key)} columnKey={c.key}>
                      {label}
                    </BoardDateLink>
                  </td>
                ) : (
                  <td
                    key={c.key}
                    className="sb-compact-empty"
                    aria-label="Not yet"
                  >
                    –
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
