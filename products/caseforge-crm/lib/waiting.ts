
export type WaitingState = "client" | "court" | "counsel";

export const WAITING_LABELS: Record<WaitingState, string> = {
  client: "WAITING FOR CLIENT",
  court: "WAITING FOR COURT",
  counsel: "WAITING FOR COUNSEL",
};

export const WAITING_LISTS: { flag: string; label: string; empty: string }[] = [
  { flag: "waiting_client", label: "Waiting for client", empty: "No one is waiting on a client right now." },
  { flag: "waiting_court", label: "Waiting for court", empty: "No one is waiting on a court right now." },
  { flag: "waiting_counsel", label: "Waiting for counsel", empty: "No one is waiting on counsel right now." },
];

export function isWaitingState(value: unknown): value is WaitingState {
  return value === "client" || value === "court" || value === "counsel";
}

export function waitingOf(value: unknown): WaitingState | undefined {
  const state = typeof value === "object" && value !== null ? (value as { state?: unknown }).state : value;
  return isWaitingState(state) ? state : undefined;
}

export function waitingLabel(state: WaitingState): string {
  return WAITING_LABELS[state];
}
