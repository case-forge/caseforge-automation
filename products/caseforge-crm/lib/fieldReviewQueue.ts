"use client";

import { useEffect, useRef, useState } from "react";
import { startVisiblePoll } from "./visiblePoll";
import type { ClientMatch, FieldReviewFlag, FieldReviewQueueResponse } from "./types";
import { backgroundFetch } from "./loadingBar";

export interface FieldReviewQueueState {
  results: ClientMatch[];
  flagsByMatter: Record<string, FieldReviewFlag[]>;
  count: number;
  loading: boolean;
  error: string | null;
  loaded: boolean;
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

const REFRESH_MS = 2 * 60 * 1000;

export function useFieldReviewQueue(refreshKey: number): FieldReviewQueueState {
  const [pollTick, setPollTick] = useState(0);

  const silentRef = useRef(false);
  const [state, setState] = useState<FieldReviewQueueState>({
    results: [],
    flagsByMatter: {},
    count: 0,
    loading: false,
    error: null,
    loaded: false,
  });

  useEffect(() => {
    const controller = new AbortController();
    const silent = silentRef.current;
    silentRef.current = false;
    setState((s) => ({ ...s, loading: !s.loaded, error: null }));
    (silent ? backgroundFetch : fetch)("/api/clients/field-review-queue", { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error("Could not load the To check list");
        return (await res.json()) as FieldReviewQueueResponse;
      })
      .then((body) => {
        setState({
          results: body.results,
          flagsByMatter: body.flags_by_matter,
          count: body.results.length,
          loading: false,
          error: null,
          loaded: true,
        });
      })
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : "Could not load the To check list" }));
      });
    return () => controller.abort();
  }, [refreshKey, pollTick]);

  useEffect(
    () =>
      startVisiblePoll(
        () => {
          silentRef.current = true;
          setPollTick((n) => n + 1);
        },
        REFRESH_MS,
        { immediate: false },
      ),
    [],
  );

  return state;
}

export const MISSING_REFERRAL_FORM = "missing_referral_form";

export function missingReferralFormOf(flags: FieldReviewFlag[] | undefined): boolean {
  return Boolean(flags?.some((f) => f.field_name === MISSING_REFERRAL_FORM));
}

export function reviewReasonOf(flags: FieldReviewFlag[] | undefined): string | null {
  flags = flags?.filter((f) => f.field_name !== MISSING_REFERRAL_FORM);
  if (!flags || flags.length === 0) return null;
  const automatic = flags.filter((f) => f.flagged_by === "Automatic" && f.note);
  const marked = flags.filter((f) => !automatic.includes(f));
  const parts: string[] = [];
  if (marked.length > 0) {
    const labels = Array.from(new Set(marked.map((f) => f.field_label || f.field_name).filter(Boolean)));
    parts.push(`Marked: ${labels.join(", ")}`);
  }
  for (const f of automatic) parts.push(f.note);
  return parts.length > 0 ? parts.join(". ") : null;
}
