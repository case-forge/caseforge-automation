"use client";

import { useEffect, useState } from "react";
import { CardBar } from "@/components/CardBar";
import { consumeRequest, isClosed, markClosed, useOpenRequests, useReportShowing } from "@/lib/cornerPrompts";
import { usePresentNode } from "@/lib/presence";
import { minimisedTabs } from "@/lib/minimisedTabs";
import { currentEditorName, loadEditorName } from "@/lib/editorName";
import { useFloatingBox } from "@/lib/useFloatingBox";
import { RESIZE_EDGES } from "@/lib/demoWindows";
import { fetchWhatsNew, loadSeen, noteDate, storeSeen, unseen, type WhatsNewItem } from "@/lib/whatsNew";

const SECTION_LIMIT = 20;

function NoteList({ items }: { items: WhatsNewItem[] }) {
  return (
    <ul className="whats-new-list">
      {items.map((item) => (
        <li key={`${item.sha}-${item.note}`}>
          <span className="whats-new-date">{noteDate(item.date)}</span>
          <span>{item.note}</span>
        </li>
      ))}
    </ul>
  );
}

export function WhatsNewPanel() {
  const [items, setItems] = useState<WhatsNewItem[]>([]);
  const [newest, setNewest] = useState("");

  const [opened, setOpened] = useState(false);
  const win = useFloatingBox("whats-new", "What's New");

  const asked = useOpenRequests("whats-new");

  useEffect(() => {
    if (isClosed("whats-new")) return;
    let cancelled = false;
    void Promise.all([fetchWhatsNew(), loadEditorName()])
      .then(([data, me]) => {
        if (cancelled || isClosed("whats-new") || data.items.length === 0) return;
        setNewest(data.items[0].sha);
        setItems(unseen(data.items, loadSeen(me)));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [asked]);

  useEffect(() => {
    if (!consumeRequest("whats-new")) return;
    let cancelled = false;
    setOpened(true);
    minimisedTabs.remove("whats-new");
    void fetchWhatsNew()
      .then((data) => {
        if (cancelled) return;
        if (data.items[0]) setNewest(data.items[0].sha);
        setItems(data.items.slice(0, SECTION_LIMIT));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [asked]);

  const shownNow = items.length > 0 || opened;

  function dismiss() {
    win.restore();
    markClosed("whats-new");
    if (newest) storeSeen(currentEditorName(), newest);
    setItems([]);
    setOpened(false);
  }
  useReportShowing("whats-new", shownNow && !win.minimised, dismiss);

  return usePresentNode(shownNow, (phase, onAnimationEnd) => (
    <aside
      ref={win.windowRef as React.RefObject<HTMLElement>}
      className={`whats-new-panel fw fw-card ${win.windowClass} widget-${phase}`}
      {...win.windowAttrs}
      role="status"
      aria-label="What's New"
      aria-hidden={win.minimised || phase === "closing" || undefined}
      style={win.style}
      onAnimationEnd={onAnimationEnd}
    >
      <CardBar
        id="whats-new"
        title="What's New"
        pinned={win.pinned}
        onClose={dismiss}
        closeHint="Close (marks these notes as seen)"
        onMinimise={win.minimise}
        barProps={win.barProps}
      />
      <div className="fw-body">
        {items.length > 0 ? <NoteList items={items} /> : <p className="whats-new-empty">Nothing new to report just now.</p>}
      </div>
      {!win.maximised && !win.pinned && RESIZE_EDGES.map((edge) => <div key={edge} className={`fw-grip fw-grip-${edge}`} aria-hidden="true" {...win.gripProps(edge)} />)}
    </aside>
  ));
}
