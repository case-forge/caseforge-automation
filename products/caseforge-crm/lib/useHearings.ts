
import { usePersistedOpen } from "./widgetOpen";
import { useCallback, useEffect, useState } from "react";
import { linkableMatterId, londonTodayIso, matterHearingsWindow, toCheckCount } from "./hearings";
import type { Hearing } from "./hearings";
import { fetchHearings, isAbort } from "./hearingsClient";
import { windowPins } from "./windowPins";

export interface HearingsRangeState {
  hearings: Hearing[];

  bankHolidays: Record<string, string>;
  needsReviewCount: number;
  openLeadsCount: number;

  toCheckCount: number;
  loading: boolean;
  error: string | null;

  loaded: boolean;
}

export function useHearingsRange(from: string | null, to: string | null, refreshKey: number): HearingsRangeState {
  const [state, setState] = useState<HearingsRangeState>({
    hearings: [],
    bankHolidays: {},
    needsReviewCount: 0,
    openLeadsCount: 0,
    toCheckCount: 0,
    loading: false,
    error: null,
    loaded: false,
  });

  useEffect(() => {
    if (!from || !to) return;
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fetchHearings(from, to, controller.signal)
      .then((body) => {
        setState({
          hearings: body.hearings,
          bankHolidays: body.bank_holidays ?? {},
          needsReviewCount: body.needs_review_count,
          openLeadsCount: body.open_leads_count ?? 0,
          toCheckCount: toCheckCount(body.needs_review_count, body.open_leads_count),
          loading: false,
          error: null,
          loaded: true,
        });
      })
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : "Could not load hearings" }));
      });
    return () => controller.abort();
  }, [from, to, refreshKey]);

  return state;
}

export interface MatterHearingsState {

  matterId: number | null;
  hearings: Hearing[];
  loading: boolean;
  error: string | null;
  loaded: boolean;
  refresh: () => void;
}

export function useMatterHearings(rawMatterId: unknown): MatterHearingsState {
  const matterId = linkableMatterId(rawMatterId);
  const [state, setState] = useState<Omit<MatterHearingsState, "matterId" | "refresh">>({ hearings: [], loading: false, error: null, loaded: false });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    setState({ hearings: [], loading: false, error: null, loaded: false });
    if (matterId === null) return;
    const controller = new AbortController();
    const { from, to } = matterHearingsWindow(londonTodayIso());
    setState((s) => ({ ...s, loading: true }));
    fetchHearings(from, to, controller.signal, matterId)
      .then((body) => setState({ hearings: body.hearings, loading: false, error: null, loaded: true }))
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : "Could not load hearings" }));
      });
    return () => controller.abort();
  }, [matterId, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { matterId, ...state, refresh };
}

export const RAIL_WINDOW_ID = "hearings-rail";

export function useRailOpen(): [boolean, (next: boolean) => void] {
  const [stored, setStored] = usePersistedOpen(RAIL_WINDOW_ID);
  const [pinnedOpen, setPinnedOpen] = useState(false);

  useEffect(() => {
    if (windowPins.isPinned(RAIL_WINDOW_ID)) setPinnedOpen(true);
  }, []);
  return [
    stored || pinnedOpen,
    (next) => {
      setStored(next);
      if (!next) setPinnedOpen(false);
    },
  ];
}
