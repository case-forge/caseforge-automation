"use client";

import { IconArrowDown, IconArrowUp } from "./icons";
import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { fetchClientSearch, isAbortError, looksLikeStaleSession } from "@/lib/clientSearch";
import { loadRecentlyViewed } from "@/lib/recentlyViewed";
import { markSessionStale } from "@/lib/sessionStale";
import { SWITCHER_DEBOUNCE_MS, SWITCHER_LIMIT, switcherMode, switcherStatus } from "@/lib/quickSwitcher";
import { concludedStatus, fullNameOf, matchKey } from "@/lib/types";
import type { ClientMatch } from "@/lib/types";
import { highlightName } from "./ResultsList";
import { SameNameSuffix } from "./SameNameLabel";

export default function QuickSwitcher({
  open,
  onOpenChange,
  onOpenMatch,
  onOpenRecent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;

  onOpenMatch: (match: ClientMatch, query: string) => void;

  onOpenRecent: (match: ClientMatch, all: ClientMatch[]) => void;
}) {

  const [query, setQuery] = useState("");
  const [recent] = useState<ClientMatch[]>(() => loadRecentlyViewed().map((entry) => entry.match));

  const [answer, setAnswer] = useState<{ query: string; results: ClientMatch[]; error: string | null } | null>(null);
  const [highlighted, setHighlighted] = useState("");

  const mode = switcherMode(query);
  const trimmed = query.trim();

  const [returnFocus] = useState(() => (typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null));
  useEffect(
    () => () => {
      window.setTimeout(() => {
        if (returnFocus?.isConnected && document.activeElement === document.body) returnFocus.focus();
      }, 0);
    },
    [returnFocus],
  );

  useEffect(() => {
    if (mode !== "search") return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchClientSearch(trimmed, SWITCHER_LIMIT, controller.signal)
        .then((body) => setAnswer({ query: trimmed, results: body.results.slice(0, SWITCHER_LIMIT), error: null }))
        .catch((err: unknown) => {
          if (isAbortError(err)) return;
          if (looksLikeStaleSession(err)) markSessionStale();
          setAnswer({ query: trimmed, results: [], error: err instanceof Error ? err.message : "Search failed" });
        });
    }, SWITCHER_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [mode, trimmed]);

  const loading = mode === "search" && answer?.query !== trimmed;
  const error = mode === "search" && answer?.query === trimmed ? answer.error : null;
  const rows = mode === "recent" ? recent : (answer?.results ?? []);
  const status = switcherStatus({ mode, query, loading, error, count: rows.length });

  const keys = rows.map((match, index) => matchKey(match, index));
  const current = keys.includes(highlighted) ? highlighted : (keys[0] ?? "");

  function choose(match: ClientMatch) {
    onOpenChange(false);
    if (mode === "recent") onOpenRecent(match, recent);

    else onOpenMatch(match, answer?.query ?? trimmed);
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Find a client"
      shouldFilter={false}
      vimBindings={false}
      loop
      value={current}
      onValueChange={setHighlighted}
      overlayClassName="switcher-overlay"
      contentClassName="switcher"
    >
      <Command.Input
        className="switcher-input"
        value={query}
        onValueChange={setQuery}
        placeholder="Find a client: name, court reference, email or phone"
        aria-label="Find a client"
      />
      <Command.List className="switcher-list" label={mode === "recent" ? "Recently viewed" : "Clients"}>
        {mode === "recent" && rows.length > 0 && <div className="switcher-heading">Recently viewed</div>}
        {rows.map((match, index) => {
          const concluded = concludedStatus(match);
          const detail = [match.case_reference, concluded ? `Concluded ${concluded.source === "closed_at" ? concluded.label : ""}`.trim() : ""]
            .filter(Boolean)
            .join(" · ");
          return (
            <Command.Item key={matchKey(match, index)} value={matchKey(match, index)} className="switcher-item" onSelect={() => choose(match)}>
              <span className="switcher-name">
                {mode === "search" ? highlightName(fullNameOf(match), query) : fullNameOf(match)}
                <SameNameSuffix row={match} />
              </span>
              {detail && <span className="switcher-detail">{detail}</span>}
            </Command.Item>
          );
        })}
      </Command.List>
      {status && (
        <p className={`switcher-status${error ? " switcher-status--error" : ""}`} role={error ? "alert" : "status"}>
          {status}
        </p>
      )}
      <p className="switcher-hint" aria-hidden="true">
        <kbd><IconArrowUp aria-label="Up" /></kbd> <kbd><IconArrowDown aria-label="Down" /></kbd> to move, <kbd>Enter</kbd> to open, <kbd>Esc</kbd> to close
      </p>
    </Command.Dialog>
  );
}
