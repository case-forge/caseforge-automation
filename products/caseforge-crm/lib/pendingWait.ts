
type WaitFacts = { email_state: string; stage: string; waiting_minutes?: number; overdue?: boolean };

export const LATE_MINUTES = 30;
export const OVERDUE_MINUTES = 60;

export type WaitTone = "normal" | "late" | "overdue";

export function waitTone(item: WaitFacts): WaitTone {
  const unsent = item.email_state !== "sent" || item.stage !== "done";
  if (!unsent) return "normal";
  const minutes = item.waiting_minutes ?? 0;
  if (item.overdue || minutes >= OVERDUE_MINUTES) return "overdue";
  return minutes >= LATE_MINUTES ? "late" : "normal";
}

export function waitedLabel(minutes: number): string {
  const m = Math.max(0, Math.floor(minutes));
  if (m < 60) return `${m} min`;
  const hours = Math.floor(m / 60);
  if (hours < 24) return m % 60 ? `${hours} h ${m % 60} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}

export function waitLine(item: WaitFacts): string {
  const tone = waitTone(item);
  if (tone === "normal") return "";
  const waited = waitedLabel(item.waiting_minutes ?? 0);
  return tone === "overdue"
    ? `Overdue: the pack email has still not gone, ${waited} after the button was pressed. Send it or finish it now.`
    : `Waiting ${waited} and the pack email has not gone yet.`;
}
