"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useDismiss } from "@/lib/dismiss";
import { HeaderOverflowEntry } from "./HeaderOverflow";
import { IconAutomation } from "./icons";
import { ageLabel, noticeCode, robotButtonLabel, splitNotices, tabForNotice, useRobotNotices } from "@/lib/robotNotices";
import type { OpenClientTarget } from "@/lib/robotNotices";
import { BlockedPopup } from "./BlockedPopup";

export function RobotNotices({
  onOpenClient,
}: {
  onOpenClient?: (name: string, target?: OpenClientTarget) => void;
}) {
  const { data, dismiss } = useRobotNotices();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const entryRef = useRef<HTMLButtonElement>(null);
  useDismiss(open, () => setOpen(false), rootRef, entryRef);

  if (!data) return null;
  const { blocked: shown, other } = splitNotices(data.items);
  const count = shown.length;
  const more = other.length;

  return (
    <div className="attention" ref={rootRef}>
      <BlockedPopup blocked={shown} dismiss={dismiss} onOpenClient={onOpenClient} />
      <button
        type="button"
        className="cf-btn cf-btn--flush attention-button attention-button--robot"
        data-header-measure=""
        data-active={count > 0}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={robotButtonLabel(count)}
        title="Automation notices"
        onClick={() => setOpen((v) => !v)}
      >
        <IconAutomation />
        {count > 0 && (
          <span className="attention-count" aria-hidden="true">
            {count}
          </span>
        )}
      </button>
      <HeaderOverflowEntry
        ref={entryRef}
        icon={<IconAutomation />}
        label="Automation notices"
        ariaLabel={robotButtonLabel(count)}
        count={count}
        tone="attention-button--robot"
        active={count > 0}
        expanded={open}
        onClick={() => setOpen((v) => !v)}
      />
      {open && (
        <div className="attention-panel" role="dialog" aria-label="Automation notices">
          <h2 className="attention-panel-title">Automation notices</h2>
          {shown.length === 0 ? (
            <p className="attention-empty">Case flow is not stuck on anything.</p>
          ) : (
            <ul className="attention-list">
              {shown.map((notice) => (
                <li key={notice.notice_id} className="attention-item" data-kind="robot">
                  <div className="attention-item-head">
                    <span className="attention-item-who">{notice.title.replace(/\s*\(CF-[A-Z]+-\d\d\)$/, "")}</span>
                    {noticeCode(notice.title) && <span className="attention-item-pill">{noticeCode(notice.title)}</span>}
                    {notice.client_name && <span className="attention-item-pill">{notice.client_name}</span>}
                    <span className="attention-item-date">{ageLabel(notice.created_utc)}</span>
                  </div>
                  {notice.detail && <p className="attention-item-summary">{notice.detail}</p>}
                  <div className="attention-item-actions">
                    {onOpenClient && notice.client_name && (
                      <button
                        type="button"
                        className="cf-btn cf-btn--link attention-item-link"
                        onClick={() => {
                          setOpen(false);
                          onOpenClient(notice.client_name, { matterId: notice.matter_id, tab: tabForNotice(notice.kind) });
                        }}
                      >
                        {tabForNotice(notice.kind) === "attendance" ? "Open client's notes" : "Open client"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="cf-btn cf-btn--link attention-item-link"
                      onClick={() => void dismiss(notice.notice_id)}
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {more > 0 && (
            <Link href="/notification-board" target="_blank" rel="noopener noreferrer" className="attention-board-link" onClick={() => setOpen(false)}>
              Other Automation notices ({more}) are on the Notification board
            </Link>
          )}
          <p className="attention-note">A notice clears itself when the step is fixed, or when you dismiss it.</p>
        </div>
      )}
    </div>
  );
}
