
import type { OpsHealthAlert } from "./opsHealth";
import type { ExpiryRow, SystemStatusResponse } from "./systemStatus";

export const REFRESH_MS = 60_000;

export const NEEDS_YOU_TITLES: RegExp[] = [
  /key spend cap/i,
  /Signed Documenso papers have not been filed/i,
  /locked folder/i,
  /classifier model is failing/i,
  /ClamAV is not answering/i,
  /signatures are \d+ days old/i,
];

export interface TieredAlerts {
  needsYou: OpsHealthAlert[];
  details: OpsHealthAlert[];
}

export function tierAlerts(alerts: OpsHealthAlert[]): TieredAlerts {
  const out: TieredAlerts = { needsYou: [], details: [] };
  for (const alert of alerts) {
    const urgent = alert.category !== "housekeeping" && (alert.severity === "red" || (alert.severity === "amber" && NEEDS_YOU_TITLES.some((re) => re.test(alert.title))));
    (urgent ? out.needsYou : out.details).push(alert);
  }
  return out;
}

const SHELL = /\b(python3?|systemctl|journalctl|sudo|ssh|gh#|az )\b|tools\/|\/root\/|\.py\b|\.json\b/i;

export function plainAction(nextAction: string): string {
  const text = (nextAction || "").trim();
  return text && !SHELL.test(text) ? text : "";
}

export interface ExpiryGroups {
  dated: ExpiryRow[];
  noExpiry: number;
}

export function groupExpiries(rows: ExpiryRow[]): ExpiryGroups {
  const dated: ExpiryRow[] = [];
  let noExpiry = 0;
  for (const row of rows) {
    if (row.state === "no_expiry") noExpiry += 1;
    else dated.push(row);
  }
  return { dated, noExpiry };
}

export function schedulesSummary(status: SystemStatusResponse): string {
  let ok = 0;
  let failed = 0;
  let overdue = 0;
  for (const box of status.workers.boxes) {
    for (const row of box.rows) {
      if (row.last_result === "failed") failed += 1;
      else if (row.overdue) overdue += 1;
      else ok += 1;
    }
  }
  const parts = [`${ok} on time`];
  if (failed) parts.push(`${failed} failed`);
  if (overdue) parts.push(`${overdue} overdue`);
  return parts.join(", ");
}

export function spendItem(spend: SystemStatusResponse["spend"]): { title: string; why: string } | null {
  if (!spend.available || spend.limit === null || spend.limit_remaining === null) return null;
  if (spend.tone !== "amber" && spend.tone !== "red") return null;
  const left = `$${spend.limit_remaining.toFixed(2)} of $${spend.limit.toFixed(2)}`;
  return {
    title: `OpenRouter key: ${left} left`,
    why: "When the cap runs out the mail classifier and other unattended model work stop. Raising the cap is your decision.",
  };
}
