"use client";

import { useEffect, useMemo, useState } from "react";
import { CardBar } from "@/components/CardBar";
import { usePresentNode } from "@/lib/presence";
import { currentEditorName, loadEditorName } from "@/lib/editorName";
import { useFloatingBox } from "@/lib/useFloatingBox";
import { RESIZE_EDGES } from "@/lib/demoWindows";
import { ageLabel, loadSeenBlocks, noticeCode, storeSeenBlocks, tabForNotice, unseenBlocks } from "@/lib/robotNotices";
import type { OpenClientTarget, RobotNotice } from "@/lib/robotNotices";

export function BlockedPopup({
  blocked,
  dismiss,
  onOpenClient,
}: {
  blocked: RobotNotice[];
  dismiss: (noticeId: string) => Promise<void>;
  onOpenClient?: (name: string, target?: OpenClientTarget) => void;
}) {
  const [seen, setSeen] = useState<string[] | null>(null);
  const win = useFloatingBox("caseflow-blocked", "Needs a person");

  useEffect(() => {
    let cancelled = false;
    void loadEditorName().then((name) => {
      if (!cancelled) setSeen(loadSeenBlocks(name));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const fresh = useMemo(() => (seen ? unseenBlocks(blocked, seen) : []), [blocked, seen]);

  const shownNow = fresh.length > 0;

  function close() {
    win.restore();
    const next = [...(seen ?? []), ...blocked.map((n) => n.notice_id)];
    storeSeenBlocks(currentEditorName(), next);
    setSeen(next);
  }

  return usePresentNode(shownNow, (phase, onAnimationEnd) => (
    <aside
      ref={win.windowRef as React.RefObject<HTMLElement>}
      className={`blocked-popup fw fw-card ${win.windowClass} widget-${phase}`}
      {...win.windowAttrs}
      role="alert"
      aria-label="Needs a person"
      aria-hidden={win.minimised || phase === "closing" || undefined}
      style={win.style}
      onAnimationEnd={onAnimationEnd}
    >
      <CardBar
        id="caseflow-blocked"
        title="Needs a person"
        pinned={win.pinned}
        onClose={close}
        closeHint="Close (the notices stay in the Automation notices icon until fixed)"
        onMinimise={win.minimise}
        barProps={win.barProps}
      />
      <div className="fw-body">
        <p className="blocked-popup-lede">
          {blocked.length === 1 ? "Something is stuck and needs a person." : `${blocked.length} things are stuck and need a person.`}
        </p>
        <ul className="blocked-popup-list">
          {blocked.map((notice) => {
            const code = noticeCode(notice.title);
            return (
              <li key={notice.notice_id} className="blocked-popup-item" data-new={fresh.some((f) => f.notice_id === notice.notice_id)}>
                <div className="blocked-popup-head">
                  <span className="blocked-popup-who">{notice.client_name || (notice.kind === "job_blocked" ? "Signed document" : "Several clients")}</span>
                  {code && <span className="blocked-popup-code">{code}</span>}
                  <span className="blocked-popup-age">{ageLabel(notice.created_utc)}</span>
                </div>
                <p className="blocked-popup-title">{notice.title.replace(/\s*\((?:CF|JOB)-[A-Z]+-\d\d\)$/, "")}</p>
                {notice.detail && <p className="blocked-popup-detail">{notice.detail}</p>}
                <div className="blocked-popup-actions">
                  {onOpenClient && notice.client_name && (
                    <button
                      type="button"
                      className="cf-btn cf-btn--link"
                      onClick={() => onOpenClient(notice.client_name, { matterId: notice.matter_id, tab: tabForNotice(notice.kind) })}
                    >
                      Open client
                    </button>
                  )}
                  <button type="button" className="cf-btn cf-btn--link" onClick={() => void dismiss(notice.notice_id)}>
                    Dismiss
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
      {!win.maximised && !win.pinned && RESIZE_EDGES.map((edge) => <div key={edge} className={`fw-grip fw-grip-${edge}`} aria-hidden="true" {...win.gripProps(edge)} />)}
    </aside>
  ));
}
