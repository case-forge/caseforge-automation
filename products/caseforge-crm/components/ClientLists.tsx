"use client";

import { useCallback, useEffect, useState } from "react";
import { DuplicatesList } from "./DuplicatesList";
import { RemovedClientsTable } from "./RemovedClientsTable";
import { ResultsList } from "./ResultsList";
import { useFieldReviewQueue } from "@/lib/fieldReviewQueue";
import { appendUnique, loadConcludedPage, loadFlagList } from "@/lib/flagLists";
import { openClientInNewTab } from "@/lib/clientLink";
import { CLIENT_LISTS, listHref, type ClientListDef, type ClientListId } from "@/lib/clientLists";
import type { ClientMatch } from "@/lib/types";
import { fullNameOf } from "@/lib/types";

export function openListClient(match: ClientMatch) {
  openClientInNewTab(fullNameOf(match), match.matter_id != null ? { matterId: String(match.matter_id) } : undefined);
}

function Concluded() {
  const [results, setResults] = useState<ClientMatch[]>([]);
  const [total, setTotal] = useState(0);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadConcludedPage(0)
      .then((page) => {
        if (cancelled) return;
        setResults(page.results);
        setTotal(page.total);
        setNext(page.nextOffset);
      })
      .catch((err: unknown) => !cancelled && setError(err instanceof Error ? err.message : "Could not load the concluded clients."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const loadMore = useCallback(async () => {
    if (next === null || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await loadConcludedPage(next);
      setResults((current) => appendUnique(current, page.results));
      setTotal(page.total);
      setNext(page.nextOffset);
    } catch {
      setNext(null);
    } finally {
      setLoadingMore(false);
    }
  }, [next, loadingMore]);

  return (
    <ResultsList
      results={results}
      count={total}
      loading={loading}
      error={error}
      query=""
      listSource="Concluded"
      selectedKey={null}
      onSelect={openListClient}
      onLoadMore={next !== null ? () => void loadMore() : undefined}
      loadingMore={loadingMore}
    />
  );
}

function ToCheck() {
  const queue = useFieldReviewQueue(0);
  return (
    <ResultsList
      results={queue.results}
      count={queue.count}
      loading={queue.loading}
      error={queue.error}
      query=""
      listSource="To check"
      reviewFlagsByMatter={queue.flagsByMatter}
      selectedKey={null}
      onSelect={openListClient}
    />
  );
}

function FlagList({ list }: { list: ClientListDef }) {
  const [results, setResults] = useState<ClientMatch[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void loadFlagList(list.flag ?? "").then((rows) => {
      if (cancelled) return;
      setResults(rows);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [list.flag]);

  return (
    <ResultsList
      results={results}
      count={results.length}
      loading={loading}
      error={null}
      query=""
      listSource={list.label}
      selectedKey={null}
      onSelect={openListClient}
    />
  );
}

export function ClientLists({ initial = "to-check" }: { initial?: ClientListId }) {
  const [list, setList] = useState<ClientListId>(initial);

  function choose(next: ClientListId) {
    setList(next);
    window.history.replaceState(null, "", listHref(next));
  }

  const current = CLIENT_LISTS.find((l) => l.id === list) ?? CLIENT_LISTS[0];

  return (
    <div className="client-lists">
      <h1>Client Lists</h1>
      <div className="client-lists-tabs" role="group" aria-label="Client lists">
        {CLIENT_LISTS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className="cf-btn cf-btn--neutral view-tab"
            aria-pressed={list === id}
            onClick={() => choose(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {current.id === "concluded" ? (
        <Concluded />
      ) : current.id === "duplicates" ? (
        <DuplicatesList />
      ) : current.id === "removed" || current.id === "merged" ? (
        <RemovedClientsTable key={current.id} show={current.id} />
      ) : current.flag ? (
        <FlagList key={current.id} list={current} />
      ) : (
        <ToCheck />
      )}
    </div>
  );
}
