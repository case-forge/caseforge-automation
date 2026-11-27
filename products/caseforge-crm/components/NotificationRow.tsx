"use client";

import { LeadGlyphText } from "./Glyphs";
import { IconAlert, IconEnvelope, IconPerson } from "./icons";
import { useState } from "react";
import { canComplete, canOpenClient, canOpenObligation, complaintPill, obligationDetail, obligationUrgencyLabel, isCourtItem, bellItemWhen } from "@/lib/attention";
import { categoryWords, notificationTitle, notificationTone, rowActions, statusLine } from "@/lib/notifications";
import type { Notification, NotificationState } from "@/lib/notifications";
import type { OpenClientTarget } from "@/lib/robotNotices";
import { hideStatementReply } from "@/lib/statementReplies";
import { formatDateForDisplay } from "@/lib/types";
import { DoneButton } from "./AttentionDone";
import type { DoneState } from "./AttentionDone";
import { CourtBadge, SpecialSenderBadge } from "./SenderBadge";
import { specialSender } from "@/lib/notificationRules";
import { useSpecialSenders } from "@/lib/specialSenders";
import { SameNameHint, SameNameSuffix } from "./SameNameLabel";

type OpenClient = (name: string, target?: OpenClientTarget) => void;

export interface RowProps {
  n: Notification;
  done: DoneState;

  onOpenClient?: OpenClient;

  onNavigate?: () => void;

  onState: (nid: string, state: NotificationState) => void;
  busyNid: string;

  showStatus?: boolean;
}

function Pills({ n }: { n: Notification }) {
  if (n.source === "attention") {
    const item = n.item;
    return (
      <>
        {item.kind === "complaint" && item.severity !== "soft" ? (
          <span className="attention-item-pill attention-item-pill--complaint">
            <IconAlert aria-hidden="true" />{" "}
            {complaintPill(item.complaint_domain)}
          </span>
        ) : (
          <span className="attention-item-pill"><LeadGlyphText label={categoryWords(n.category)} /></span>
        )}
        {item.importance === "high" && item.kind !== "complaint" && <span className="attention-item-pill">Urgent</span>}
      </>
    );
  }
  if (n.source === "obligation") return <span className="attention-item-pill">{obligationUrgencyLabel(n.item.urgency)}</span>;
  if (n.source === "new_matter") return <span className="attention-item-pill">New client</span>;
  return <span className="attention-item-pill"><LeadGlyphText label={categoryWords(n.category)} /></span>;
}

function When({ n }: { n: Notification }) {
  if (n.source === "obligation") {
    return n.item.hearing_date ? <span className="attention-item-date">Hearing {formatDateForDisplay(n.item.hearing_date)}</span> : null;
  }
  const when = bellItemWhen(n.created);
  if (!when) return null;
  return (
    <time className="attention-item-date" dateTime={n.created} title={when.exact}>
      {when.label}
    </time>
  );
}

function StatementDone({ n }: { n: Extract<Notification, { source: "statement" }> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function hide() {
    setError("");
    setBusy(true);
    try {
      await hideStatementReply(n.matter_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mark that done.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button type="button" className="cf-btn cf-btn--neutral cf-btn--small attention-item-done" disabled={busy} title="Dealt with, for everyone: it leaves the lists and stays on record. Nothing is sent or deleted." onClick={() => void hide()}>
        {busy ? "Saving..." : "Done"}
      </button>
      {error && (
        <p className="todo-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

export function NotificationRow({ n, done, onOpenClient, onNavigate, onState, busyNid, showStatus = false }: RowProps) {
  const tone = notificationTone(n);
  const status = showStatus ? statusLine(n) : "";
  const open = (name: string, matterId: string) => {
    onNavigate?.();
    onOpenClient?.(name, matterId ? { matterId } : undefined);
  };

  const sameName = n.source === "attention" || n.source === "obligation" || n.source === "new_matter" ? n.item : null;

  const special = specialSender(n, useSpecialSenders());
  return (
    <li className="attention-item" data-kind={n.category} data-source={n.source} data-tone={tone} data-urgency={n.source === "obligation" ? n.item.urgency : undefined}>
      <div className="attention-item-head">
        <span className="attention-item-who-line">
          {special && <SpecialSenderBadge sender={special.sender} />}
          {n.source === "attention" && isCourtItem(n.item) && <CourtBadge />}
          <span className="attention-item-who">
            {notificationTitle(n)}
            <SameNameSuffix row={sameName} />
          </span>
        </span>
        <Pills n={n} />
        <When n={n} />
      </div>
      <SameNameHint row={sameName} className="attention-item-summary" />
      {n.source === "attention" && <p className="attention-item-summary">{n.item.summary || n.item.subject || "Email needs review"}</p>}
      {n.source === "attention" && n.item.deadline && <p className="attention-item-deadline">Deadline: {n.item.deadline}</p>}
      {n.source === "obligation" && n.item.label && <p className="attention-item-summary">{n.item.label}</p>}
      {n.source === "obligation" && obligationDetail(n.item) && <p className="attention-item-summary">{obligationDetail(n.item)}</p>}
      {n.source === "statement" && n.item.state === "amend" && n.item.note && <p className="attention-item-summary">{n.item.note}</p>}
      {status && <p className="attention-note notification-status">{status}</p>}
      <div className="attention-item-actions">
        {n.source === "attention" && n.item.web_link && (
          <a className="cf-btn cf-btn--link attention-item-link" href={n.item.web_link} target="_blank" rel="noreferrer">
            <IconEnvelope aria-hidden="true" /> Open email
          </a>
        )}
        {onOpenClient && n.source === "attention" && canOpenClient(n.item) && (
          <button type="button" className="cf-btn cf-btn--link attention-item-link" onClick={() => open(n.item.who, n.matter_id)}>
            <IconPerson aria-hidden="true" /> Open client
          </button>
        )}
        {onOpenClient && n.source === "obligation" && canOpenObligation(n.item) && (
          <button type="button" className="cf-btn cf-btn--link attention-item-link" onClick={() => open(n.item.client, String(n.item.matter_id))}>
            <IconPerson aria-hidden="true" /> Open client
          </button>
        )}
        {onOpenClient && (n.source === "statement" || n.source === "new_matter") && n.client.trim() !== "" && (
          <button type="button" className="cf-btn cf-btn--link attention-item-link" onClick={() => open(n.client, n.matter_id)}>
            <IconPerson aria-hidden="true" /> Open client
          </button>
        )}
        {n.source === "statement" && n.item.by && <span className="reply-by">Recorded by {n.item.by}</span>}
        {n.source === "attention" && canComplete(n.item) && <DoneButton item={n.item} state={done} />}
        {n.source === "statement" && <StatementDone n={n} />}
        {rowActions(n.status).map((action) => (
          <button
            key={action.state}
            type="button"
            className="cf-btn cf-btn--neutral cf-btn--small attention-item-done notification-state-button"
            disabled={busyNid === n.nid}
            title={action.title}
            onClick={() => onState(n.nid, action.state)}
          >
            {action.label}
          </button>
        ))}
      </div>
    </li>
  );
}
