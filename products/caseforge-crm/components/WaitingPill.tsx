import { waitingLabel, type WaitingState } from "@/lib/waiting";

export function WaitingPill({ state, compact = false }: { state: WaitingState; compact?: boolean }) {
  return (
    <span className="waiting-pill" data-waiting={state} data-compact={compact ? "true" : undefined} role="status">
      {waitingLabel(state)}
    </span>
  );
}
