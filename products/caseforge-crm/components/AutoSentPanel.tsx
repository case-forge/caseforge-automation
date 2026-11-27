"use client";

import { useEffect, useRef, useState } from "react";
import { refreshAutoSend, useAutoSendData } from "@/lib/autoSendStore";
import { useDismiss } from "@/lib/dismiss";
import { DISMISS_FAILED_LINE, DISMISS_HINT, EMPTY_LINE, TABS, canDismiss, dismissLabel, forMatter, withoutDismissed, UNAVAILABLE_LINE, groupItems, safeLink, stateLabel, tabLabel } from "@/lib/autoSend";
import type { AutoSendItem, AutoSendState } from "@/lib/autoSend";

const TICK_MS = 15_000;

export function AutoSentPanel({
  tab,
  onTab,
  matterId,
  idPrefix = "as",
}: {
  tab: AutoSendState;
  onTab: (next: AutoSendState) => void;

  matterId?: string;

  idPrefix?: string;
}) {
  const load = useAutoSendData();
  const setTab = onTab;
  const [openId, setOpenId] = useState("");

  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [dismissError, setDismissError] = useState("");
  const [now, setNow] = useState(() => new Date());
  const rootRef = useRef<HTMLDivElement>(null);

  useDismiss(openId !== "", () => setOpenId(""), rootRef);

  useEffect(() => {
    const tick = window.setInterval(() => setNow(new Date()), TICK_MS);
    return () => window.clearInterval(tick);
  }, []);

  if (load.status === "loading") return <p className="teaser-muted">Loading…</p>;
  if (load.status === "unavailable") return <p className="teaser-muted">{UNAVAILABLE_LINE}</p>;
  if (load.status === "failed") return <p className="teaser-muted" role="alert">This overview could not be loaded.</p>;

  const groups = groupItems(withoutDismissed(matterId ? forMatter(load.items, matterId) : load.items, hidden));

  async function dismiss(item: AutoSendItem) {
    setDismissError("");
    setHidden((h) => new Set(h).add(item.id));
    if (openId === item.id) setOpenId("");
    try {
      const res = await fetch("/api/auto-send/dismiss", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: item.id }) });
      if (!res.ok) throw new Error("dismiss");
      void refreshAutoSend();
    } catch {
      setHidden((h) => {
        const next = new Set(h);
        next.delete(item.id);
        return next;
      });
      setDismissError(DISMISS_FAILED_LINE);
    }
  }
  const rows = groups[tab];

  function onTabKey(e: React.KeyboardEvent, index: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = TABS[(index + step + TABS.length) % TABS.length].state;
    setTab(next);
    setOpenId("");
    document.getElementById(`${idPrefix}-tab-${next}`)?.focus();
  }

  return (
    <div className="as-panel" ref={rootRef}>
      <div role="tablist" aria-label="Auto Send emails" className="as-tabs">
        {TABS.map((t, i) => (
          <button
            key={t.state}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${t.state}`}
            aria-selected={tab === t.state}
            aria-controls={`${idPrefix}-tabpanel`}
            tabIndex={tab === t.state ? 0 : -1}
            className={`cf-btn cf-btn--flush as-tab as-tab--${t.state}`}
            onClick={() => {
              setTab(t.state);
              setOpenId("");
            }}
            onKeyDown={(e) => onTabKey(e, i)}
          >
            {tabLabel(t.label, groups[t.state].length)}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${idPrefix}-tabpanel`} aria-labelledby={`${idPrefix}-tab-${tab}`}>
        {dismissError && (
          <p className="teaser-muted" role="alert">
            {dismissError}
          </p>
        )}
        {rows.length === 0 ? (
          <p className="teaser-muted">{EMPTY_LINE}</p>
        ) : (
          <ul className="as-list">
            {rows.map((item) => {
              const open = openId === item.id;
              return (
                <li key={item.id} className={`as-row as-row--${item.state}`}>
                  <button type="button" className="as-row-btn" aria-expanded={open} aria-controls={`${idPrefix}-prev-${item.id}`} onClick={() => setOpenId(open ? "" : item.id)}>
                    <span className="as-client">
                      <span className="as-matter">{item.matter_id}</span> {item.client_name}
                    </span>
                    <span className="as-subject">{item.subject}</span>
                    <span className="as-to">{item.recipients.join(", ")}</span>
                    <span className="as-class">{item.class}</span>
                    <span className={`as-state as-state--${item.state}`}>{stateLabel(item, now)}</span>
                  </button>
                  {canDismiss(item) && (
                    <button type="button" className="cf-btn cf-btn--neutral as-dismiss" aria-label={dismissLabel(item.subject)} title={DISMISS_HINT} onClick={() => void dismiss(item)}>
                      Dismiss
                    </button>
                  )}
                  {open && <Preview item={item} idPrefix={idPrefix} />}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

function Preview({ item, idPrefix }: { item: AutoSendItem; idPrefix: string }) {
  const sent = safeLink(item.outlook_link);
  const filed = safeLink(item.sharepoint_link);
  return (
    <div className="as-preview" id={`${idPrefix}-prev-${item.id}`} role="region" aria-label={`Preview of ${item.subject}`}>
      <dl className="as-preview-head">
        <dt>Subject</dt>
        <dd>{item.subject}</dd>
        <dt>To</dt>
        <dd>{item.recipients.join(", ")}</dd>
      </dl>
      <pre className="as-body">{item.body_text || "No text is held for this email."}</pre>
      {item.state === "left" && (sent || filed) && (
        <p className="as-links">
          {sent && (
            <a href={sent} target="_blank" rel="noopener noreferrer">
              Open the sent copy
            </a>
          )}
          {filed && (
            <a href={filed} target="_blank" rel="noopener noreferrer">
              Open the filed copy
            </a>
          )}
        </p>
      )}
    </div>
  );
}
