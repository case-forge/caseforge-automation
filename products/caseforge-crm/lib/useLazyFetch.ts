"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface LazyResult<T> {
  data: T | null;
  failed: boolean;
}

export interface LazyStored<T> extends LazyResult<T> {
  url: string | null;
}

export const NOTHING: LazyResult<never> = { data: null, failed: false };

export function startLazyFetch<T>(
  url: string,
  onResult: (result: LazyResult<T>) => void,
  fetcher: (url: string) => Promise<Response> = (u) => fetch(u),
): () => void {
  let cancelled = false;
  fetcher(url)
    .then((res) => {
      if (!res.ok) throw new Error(`request failed: ${res.status}`);
      return res.json() as Promise<T>;
    })
    .then((data) => {
      if (!cancelled) onResult({ data, failed: false });
    })
    .catch(() => {
      if (!cancelled) onResult({ data: null, failed: true });
    });
  return () => {
    cancelled = true;
  };
}

export function resultFor<T>(stored: LazyStored<T>, url: string | null): LazyResult<T> {
  if (!url || stored.url !== url) return NOTHING;
  return { data: stored.data, failed: stored.failed };
}

export const GRAPH_READ_CACHE_MS = 3 * 60_000;

const answers = new Map<string, { at: number; data: unknown }>();

export function cachedAnswer<T>(url: string, maxAgeMs: number, now: number = Date.now()): T | undefined {
  const kept = answers.get(url);
  if (!kept) return undefined;
  if (now - kept.at >= maxAgeMs) {
    answers.delete(url);
    return undefined;
  }
  return kept.data as T;
}

export function rememberAnswer(url: string, data: unknown, now: number = Date.now()): void {
  if (data === null || data === undefined) answers.delete(url);
  else answers.set(url, { at: now, data });
}

export function forgetAnswers(): void {
  answers.clear();
}

export interface LazyFetchOptions {

  refreshKey?: unknown;

  refreshEvent?: string;

  refreshWhen?: (event: Event) => boolean;

  cacheMs?: number;

  fetcher?: (url: string) => Promise<Response>;
}

export interface LazyFetch<T> extends LazyResult<T> {

  loading: boolean;

  setData: (next: T | null | ((current: T | null) => T | null)) => void;
}

export function useLazyFetch<T>(url: string | null, options: LazyFetchOptions = {}): LazyFetch<T> {
  const { refreshKey, refreshEvent, cacheMs } = options;
  const [stored, setStored] = useState<LazyStored<T>>({ url: null, data: null, failed: false });
  const [tick, setTick] = useState(0);

  const cached = cacheMs && url && stored.url !== url ? cachedAnswer<T>(url, cacheMs) : undefined;

  const lastRead = useRef<{ url: string | null; refreshKey: unknown; tick: number } | null>(null);

  const refreshWhen = useRef(options.refreshWhen);
  const fetcher = useRef(options.fetcher);
  useEffect(() => {
    refreshWhen.current = options.refreshWhen;
    fetcher.current = options.fetcher;
  });

  useEffect(() => {
    if (!url) return;
    const last = lastRead.current;
    const refreshing = !!last && last.url === url && (last.refreshKey !== refreshKey || last.tick !== tick);
    lastRead.current = { url, refreshKey, tick };
    const kept = cacheMs && !refreshing ? cachedAnswer<T>(url, cacheMs) : undefined;
    if (kept !== undefined) {

      setStored({ url, data: kept, failed: false });
      return;
    }
    return startLazyFetch<T>(url, (result) => {
      if (cacheMs && !result.failed) rememberAnswer(url, result.data);
      setStored({ url, ...result });
    }, fetcher.current);
  }, [url, refreshKey, tick, cacheMs]);

  useEffect(() => {
    if (!url || !refreshEvent) return;
    function onEvent(event: Event) {
      if (!refreshWhen.current || refreshWhen.current(event)) setTick((n) => n + 1);
    }
    window.addEventListener(refreshEvent, onEvent);
    return () => window.removeEventListener(refreshEvent, onEvent);
  }, [url, refreshEvent]);

  const setData = useCallback(
    (next: T | null | ((current: T | null) => T | null)) =>
      setStored((prev) => {
        const current = prev.url === url ? prev.data : url && cacheMs ? (cachedAnswer<T>(url, cacheMs) ?? null) : null;
        const data = typeof next === "function" ? (next as (current: T | null) => T | null)(current) : next;
        if (url && cacheMs) rememberAnswer(url, data);
        return { url, data, failed: false };
      }),
    [url, cacheMs],
  );

  if (cached !== undefined) return { data: cached, failed: false, loading: false, setData };
  const result = resultFor(stored, url);
  return { ...result, loading: !!url && stored.url !== url, setData };
}
