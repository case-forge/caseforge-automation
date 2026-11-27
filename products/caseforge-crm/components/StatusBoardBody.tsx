"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBoardTable } from "./StatusBoardCompact";
import { IconArrowRight, IconExternalLink, IconRefresh } from "./icons";
import { EXPORT_BOARD_URL } from "@/lib/firmLinks";
import { FAILURE_LINE, findTeaser } from "@/lib/frontPageTeasers";
import type { TeaserSummary } from "@/lib/frontPageTeasers";

type Loaded = { state: "loading" } | { state: "failed" } | { state: "ready"; summary: TeaserSummary; at: Date };

const updatedAt = (at: Date) => at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

export function StatusBoardBody({ reloadRef }: { reloadRef?: { current: (() => void) | null } }) {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(() => {
    const teaser = findTeaser("status-board");
    if (!teaser) return;
    setRefreshing(true);
    teaser
      .load()
      .then((summary) => setLoaded({ state: "ready", summary, at: new Date() }))
      .catch(() => setLoaded((l) => (l.state === "ready" ? l : { state: "failed" })))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    load();
    if (reloadRef) reloadRef.current = load;
    return () => {
      if (reloadRef) reloadRef.current = null;
    };
  }, [load, reloadRef]);

  return (
    <>
      {loaded.state === "loading" && <p className="teaser-muted">Loading…</p>}
      {loaded.state === "failed" && (
        <p className="teaser-muted" role="alert">
          {FAILURE_LINE}
        </p>
      )}
      {loaded.state === "ready" &&
        (loaded.summary.rows && loaded.summary.rows.length > 0 ? <StatusBoardTable items={loaded.summary.rows} onChanged={load} /> : <p className="teaser-muted">No open matters yet.</p>)}
      <div className="teaser-actions">
        <a className="cf-btn cf-btn--secondary teaser-open" href="/status-board">
          Open Full Status Board <IconArrowRight aria-hidden="true" />
        </a>
        <span className="teaser-refresh">
          <button type="button" className="cf-btn cf-btn--secondary teaser-open" disabled={refreshing} onClick={load}>
            <IconRefresh aria-hidden="true" /> {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          {loaded.state === "ready" && <span className="teaser-muted teaser-updated">Updated {updatedAt(loaded.at)}</span>}
        </span>
        <a className="cf-btn cf-btn--secondary teaser-open" href={EXPORT_BOARD_URL} target="_blank" rel="noopener noreferrer">
          Open Export Board <IconExternalLink aria-hidden="true" />
          <span className="review-mail-sr"> (opens in a new tab)</span>
        </a>
      </div>
    </>
  );
}
