"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useDismiss } from "@/lib/dismiss";
import { useTitleBadge } from "@/lib/useTitleBadge";
import { HeaderOverflowEntry } from "./HeaderOverflow";
import type { OpenClientTarget } from "@/lib/robotNotices";
import { useAttention } from "@/lib/useAttention";
import { BELL_DAYS, complaintCount, notificationsLabel, orderForBell, setNotificationState, urgentOnly, useNotifications } from "@/lib/notifications";
import type { NotificationState } from "@/lib/notifications";
import { DoneBar, useAttentionDone } from "./AttentionDone";
import { IconBell } from "./icons";
import { NotificationRow } from "./NotificationRow";

type OpenClient = (name: string, target?: OpenClientTarget) => void;

export function AttentionBell({ onOpenClient }: { onOpenClient?: OpenClient }) {
  const attention = useAttention();
  const view = useNotifications();
  const done = useAttentionDone();
  const [open, setOpen] = useState(false);
  const [busyNid, setBusyNid] = useState("");
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const entryRef = useRef<HTMLButtonElement>(null);
  useDismiss(open, () => setOpen(false), rootRef, entryRef);

  const urgent = view ? urgentOnly(view) : null;
  useTitleBadge(urgent?.counts.bell ?? 0);

  if (!view || !urgent) return null;

  const list = orderForBell(urgent.bell);
  const total = urgent.counts.bell;
  const complaints = complaintCount(urgent.bell);
  const older = urgent.counts.board;
  const label = notificationsLabel(total, complaints, older);
  const attentionItems = list.flatMap((n) => (n.source === "attention" ? [n.item] : []));

  async function change(nid: string, state: NotificationState) {
    setError("");
    setBusyNid(nid);
    try {
      await setNotificationState(nid, state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that.");
    } finally {
      setBusyNid("");
    }
  }

  return (
    <div className="attention" ref={rootRef}>
      <button
        type="button"
        className="cf-btn cf-btn--flush attention-button attention-button--yellow"
        data-header-measure=""
        data-active={total > 0}
        data-complaint={complaints > 0}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={label}
        title="Notifications"
        onClick={() => setOpen((v) => !v)}
      >
        <IconBell aria-hidden="true" />
        {total > 0 && (
          <span className="attention-count" aria-hidden="true">
            {total}
          </span>
        )}
      </button>
      <HeaderOverflowEntry
        ref={entryRef}
        icon={<IconBell aria-hidden="true" />}
        label="Notifications"
        ariaLabel={label}
        count={total}
        tone="attention-button--yellow"
        active={total > 0}
        complaint={complaints > 0}
        expanded={open}
        onClick={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="attention-panel" role="dialog" aria-label="Notifications">
          <h2 className="attention-panel-title">Notifications</h2>
          <DoneBar state={done} items={attentionItems} />
          {error && (
            <p className="todo-error" role="alert">
              {error}
            </p>
          )}
          {list.length === 0 ? (
            <p className="attention-empty">
              {`Nothing new in the last ${BELL_DAYS} days.`}
            </p>
          ) : (
            <ul className="attention-list">
              {list.map((n) => (
                <NotificationRow
                  key={n.nid}
                  n={n}
                  done={done}
                  onOpenClient={onOpenClient}
                  onNavigate={() => setOpen(false)}
                  onState={(nid, state) => void change(nid, state)}
                  busyNid={busyNid}
                />
              ))}
            </ul>
          )}
          {attention?.obligations_error && <p className="attention-note">Aged obligations could not be read just now.</p>}
          <Link href="/notification-board" target="_blank" rel="noopener noreferrer" className="attention-board-link" onClick={() => setOpen(false)}>
            Notification board{older > 0 ? ` (${older} more)` : ""}
          </Link>
          <p className="attention-note">
            The last {BELL_DAYS} days only. Older notifications, and the ones you dismiss or hide, are on the Notification board. Dismiss and Hide
            affect only your own bell. Done closes a notification for everyone.
          </p>
        </div>
      )}
    </div>
  );
}
