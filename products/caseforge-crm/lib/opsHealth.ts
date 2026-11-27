
export type OpsSeverity = "red" | "amber" | "info" | "green" | "unknown";

export interface OpsHealthAlert {
  severity: OpsSeverity;
  category: "health" | "housekeeping";
  title: string;
  next_action: string;
  kind: string;
  age_minutes: number | null;
}

export interface OpsHealthResponse {
  available: boolean;
  generated_at: string;
  snapshot_age_minutes: number | null;
  stale: boolean;
  overall_severity: OpsSeverity;
  housekeeping_severity: OpsSeverity;
  alerts: OpsHealthAlert[];
}

export type OpsHealthLoad =
  | { state: "hidden" }
  | { state: "error" }
  | { state: "ok"; data: OpsHealthResponse };

export async function loadOpsHealth(fetcher: typeof fetch = fetch): Promise<OpsHealthLoad> {
  try {
    const res = await fetcher("/api/ops-health", { cache: "no-store" });
    if (res.status === 403) return { state: "hidden" };
    if (!res.ok) return { state: "error" };
    return { state: "ok", data: (await res.json()) as OpsHealthResponse };
  } catch {
    return { state: "error" };
  }
}

type Overall = { label: string; line: string; tone: "attention" | "look" | "clear" | "unknown" };

export function overallLabel(data: OpsHealthResponse): Overall {
  const current = currentLabel(data);
  if (!data.available || !data.stale) return current;
  return { ...current, line: `At the last check: ${current.line.charAt(0).toLowerCase()}${current.line.slice(1)}` };
}

function currentLabel(data: OpsHealthResponse): Overall {
  if (!data.available) {
    return { label: "No report yet", line: "The health check has not written a report on this server yet.", tone: "unknown" };
  }
  switch (data.overall_severity) {
    case "red":
      return { label: "Needs attention", line: "Something is not working and needs someone to look at it.", tone: "attention" };
    case "amber":
      return { label: "Worth a look", line: "Everything is working. A few things are worth a look when there is time.", tone: "look" };
    case "green":
    case "info":
      return { label: "All clear", line: "Everything is working.", tone: "clear" };
    default:
      return { label: "Not known", line: "The last report did not say how things are.", tone: "unknown" };
  }
}

export function settingsSummary(data: OpsHealthResponse): string {
  const { label } = overallLabel(data);
  return data.available && data.stale ? `${label}, out of date` : label;
}

export function durationLabel(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes) || minutes < 0) return "";
  const m = Math.round(minutes);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min`;
  if (m < 48 * 60) {
    const h = Math.floor(m / 60);
    const rest = m % 60;
    return rest ? `${h} h ${rest} min` : `${h} h`;
  }
  const days = Math.round(m / 1440);
  return `${days} days`;
}

export function checkedLabel(data: OpsHealthResponse): string {
  if (!data.available) return "";
  const when = new Date(data.generated_at);
  const ago = durationLabel(data.snapshot_age_minutes);
  if (Number.isNaN(when.getTime())) return "Checked at an unknown time.";
  const clock = when.toLocaleString("en-GB", {
    timeZone: "Europe/London",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `Last checked ${clock}${ago ? ` (${ago === "just now" ? "just now" : `${ago} ago`})` : ""}.`;
}

export interface OpsHealthGroups {
  attention: OpsHealthAlert[];
  look: OpsHealthAlert[];
  info: OpsHealthAlert[];
  housekeeping: OpsHealthAlert[];
}

export function groupAlerts(alerts: OpsHealthAlert[]): OpsHealthGroups {
  const groups: OpsHealthGroups = { attention: [], look: [], info: [], housekeeping: [] };
  for (const alert of alerts) {
    if (alert.category === "housekeeping") groups.housekeeping.push(alert);
    else if (alert.severity === "red") groups.attention.push(alert);
    else if (alert.severity === "amber") groups.look.push(alert);
    else groups.info.push(alert);
  }
  return groups;
}
