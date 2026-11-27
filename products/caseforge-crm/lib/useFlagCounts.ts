"use client";

import { usePolledStore } from "./polledStore";
import { createPulseSlice } from "./pulse";

export const FLAGS_CHANGED_EVENT = "caseforge:flags-changed";

export function notifyFlagsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(FLAGS_CHANGED_EVENT));
}

export interface FlagCounts {
  flagged: number;
  starred: number;
}

const countsStore = createPulseSlice<FlagCounts>((pulse) =>
  pulse.flag_counts ? { flagged: pulse.flag_counts.counts?.flagged ?? 0, starred: pulse.flag_counts.counts?.starred ?? 0 } : null,
);
const NO_COUNTS: FlagCounts = { flagged: 0, starred: 0 };

export function useFlagCounts(): FlagCounts {
  return usePolledStore(countsStore).data ?? NO_COUNTS;
}
