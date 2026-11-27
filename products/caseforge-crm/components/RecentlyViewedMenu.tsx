"use client";

import { useEffect, useRef, useState } from "react";
import { useDismiss } from "@/lib/dismiss";
import { clearRecentlyViewed, forgetRecentlyViewed, loadRecentlyViewed, RECENTLY_VIEWED_CHANGED } from "@/lib/recentlyViewed";
import type { RecentlyViewedEntry } from "@/lib/recentlyViewed";
import { fullNameOf } from "@/lib/types";
import { SameNameSuffix } from "./SameNameLabel";
import type { ClientMatch } from "@/lib/types";
import { IconClock } from "./icons";

export function RecentlyViewedMenu({
  onOpen,
  onShowList,
}: {
  onOpen: (match: ClientMatch, all: ClientMatch[]) => void;
  onShowList: (matches: ClientMatch[], label: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<RecentlyViewedEntry[]>([]);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reread = () => setEntries(loadRecentlyViewed());
    reread();

    const ids = loadRecentlyViewed().map((entry) => String(entry.match.matter_id ?? "")).filter(Boolean);
    if (ids.length > 0) {
      fetch(`/api/clients/hidden?ids=${encodeURIComponent(ids.join(","))}`)
        .then((res) => (res.ok ? res.json() : { hidden: [] }))
        .then((body: { hidden?: string[] }) => forgetRecentlyViewed(body.hidden ?? []))
        .catch(() => undefined);
    }
    window.addEventListener(RECENTLY_VIEWED_CHANGED, reread);
    window.addEventListener("storage", reread);
    return () => {
      window.removeEventListener(RECENTLY_VIEWED_CHANGED, reread);
      window.removeEventListener("storage", reread);
    };
  }, []);

  useDismiss(open, () => setOpen(false), rootRef);

  function toggle() {
    if (!open) setEntries(loadRecentlyViewed());
    setOpen((value) => !value);
  }

  if (entries.length === 0) return null;

  return (
    <div className="recent-menu" ref={rootRef}>
      <button
        type="button"
        className="cf-btn cf-btn--flush view-tab view-tab--icon"
        aria-expanded={open}
        aria-label="Recently viewed"
        title="Recently viewed"
        onClick={toggle}
      >
        <IconClock className="view-tab-icon" aria-hidden="true" />
      </button>
      {open && (
        <div className="recent-menu-popover" role="group" aria-label="Recently viewed">
          {(
            <>
              <ul className="recent-menu-list">
                {entries.map((entry) => (
                  <li key={String(entry.match.matter_id ?? entry.viewedAt)}>
                    <button
                      type="button"
                      className="cf-btn cf-btn--flush cf-btn--row recent-menu-item"
                      onClick={() => {
                        setOpen(false);
                        onOpen(entry.match, entries.map((e) => e.match));
                      }}
                    >
                      {fullNameOf(entry.match)}
                      <SameNameSuffix row={entry.match} />
                    </button>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                className="cf-btn cf-btn--flush cf-btn--row recent-menu-item recent-menu-list-all"
                onClick={() => {
                  setOpen(false);
                  onShowList(entries.map((entry) => entry.match), "Recently viewed");
                }}
              >
                Show as list
              </button>
              <button
                type="button"
                className="cf-btn cf-btn--flush cf-btn--row cf-btn--danger recent-menu-item recent-menu-clear"
                onClick={() => {
                  setOpen(false);
                  clearRecentlyViewed();
                }}
              >
                Clear list
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
