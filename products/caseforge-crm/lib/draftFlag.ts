
import { notifyFlagsChanged } from "./useFlagCounts";

export const DRAFT_FLAG_REASON = "Unfinished draft";

export const MATTER_FLAGS_CHANGED_EVENT = "caseforge:matter-flags-changed";

export function draftFlagRequest(matterId: string, unfinished: boolean): Record<string, unknown> {
  return {
    matter_id: matterId,
    flag_name: "flagged",
    is_set: unfinished,
    ...(unfinished ? { reason: DRAFT_FLAG_REASON } : { only_if_reason: DRAFT_FLAG_REASON }),
  };
}

export async function setDraftFlag(matterId: string, unfinished: boolean): Promise<void> {
  if (!matterId) return;
  try {
    const res = await fetch("/api/clients/matter-flags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(draftFlagRequest(matterId, unfinished)),
    });
    if (!res.ok) return;
    notifyFlagsChanged();
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent(MATTER_FLAGS_CHANGED_EVENT, { detail: { matterId } }));
    }
  } catch {

  }
}
