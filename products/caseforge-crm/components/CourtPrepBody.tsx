"use client";

import { useCallback, useEffect, useState } from "react";
import { CourtPrepTable } from "./CourtPrepTable";
import { IconArrowRight, IconRefresh } from "./icons";
import type { CourtPrepResponse } from "@/lib/courtPrep";

type Loaded = { state: "loading" } | { state: "failed" } | { state: "ready"; board: CourtPrepResponse; at: Date };

const updatedAt = (at: Date) => at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

export function CourtPrepBody({ reloadRef, withFullLink = true }: { reloadRef?: { current: (() => void) | null }; withFullLink?: boolean }) {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(() => {
    setRefreshing(true);
    fetch("/api/court-prep", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error("court prep");
        return res.json() as Promise<CourtPrepResponse>;
      })
      .then((board) => setLoaded({ state: "ready", board: { items: Array.isArray(board.items) ? board.items : [], in_review: Number(board.in_review) || 0 }, at: new Date() }))
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
          This overview could not be loaded.
        </p>
      )}
      {loaded.state === "ready" && (loaded.board.items.length > 0 ? <CourtPrepTable items={loaded.board.items} /> : <p className="teaser-muted">No hearings in the next 14 days.</p>)}
      {loaded.state === "ready" && !!loaded.board.in_review && (
        <p className="teaser-muted">
          {loaded.board.in_review} {loaded.board.in_review === 1 ? "hearing is" : "hearings are"} waiting for review in the Hearings Panel and not shown here.
        </p>
      )}
      <div className="teaser-actions">
        {withFullLink && (
          <a className="cf-btn cf-btn--secondary teaser-open" href="/court-prep">
            Open Full Court Prep <IconArrowRight aria-hidden="true" />
          </a>
        )}
        <span className="teaser-refresh">
          <button type="button" className="cf-btn cf-btn--secondary teaser-open" disabled={refreshing} onClick={load}>
            <IconRefresh aria-hidden="true" /> {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          {loaded.state === "ready" && <span className="teaser-muted teaser-updated">Updated {updatedAt(loaded.at)}</span>}
        </span>
      </div>
    </>
  );
}
