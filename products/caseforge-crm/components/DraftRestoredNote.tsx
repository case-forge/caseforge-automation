"use client";

import { draftTimeLabel } from "@/lib/formDrafts";

export function DraftRestoredNote({
  savedAt,
  saveLabel = "Save",
  onDiscard,
}: {
  savedAt: number | null;
  saveLabel?: string;
  onDiscard: () => void;
}) {
  if (savedAt === null) return null;
  return (
    <p className="draft-restored-note" role="status">
      <span>
        Restored unsaved changes from before the refresh or leaving this form (kept at {draftTimeLabel(savedAt)}). {saveLabel} or
        Discard.
      </span>
      <button type="button" className="cf-btn cf-btn--flush" onClick={onDiscard}>
        Discard
      </button>
    </p>
  );
}
