
import type { SameNameFields } from "./sameName";

export type TodayItem = SameNameFields & {
  matter_id: string;
  client_name: string;
  [key: string]: unknown;
};

export type TodaySection = {
  key: "step_3" | "step_4" | "step_5" | "step_6" | "step_7" | "reminders" | "drafts" | "waiting_client" | "waiting_court" | "waiting_counsel" | string;
  title: string;
  count: number;
  items: TodayItem[];
  error: boolean;
};

export type TodayBoardData = {
  today: string;
  tomorrow: string;
  sections: TodaySection[];
  not_tracked?: string[];
};

export function visibleSections(data: TodayBoardData | null): TodaySection[] {
  return (data?.sections ?? []).filter((s) => s.count > 0 || s.error);
}

export function sectionHeading(section: TodaySection): string {
  if (section.error) return `${section.title}: unavailable`;
  const shown = section.items.length;
  return shown < section.count ? `${section.title} (${shown} of ${section.count})` : `${section.title} (${section.count})`;
}

export function itemLine(section: string, item: TodayItem): string {
  const s = (key: string) => String(item[key] ?? "").trim();
  switch (section) {
    case "drafts":
    case "reminders":
      return s("subject") || "(no subject)";
    case "step_3":
    case "step_4":
    case "step_5":
    case "step_6":
    case "step_7":
      return [item.state === "yours" ? "Your turn" : "Case flow", s("line")].filter(Boolean).join(" · ");
    case "waiting_client":
    case "waiting_court":
    case "waiting_counsel":
    case "pit_stops":
      return [s("label").toLowerCase().replace(/^./, (c) => c.toUpperCase()), "nothing to do until they reply"].filter(Boolean).join(" · ");
    default:
      return "";
  }
}

export function scheduledLabel(utc: unknown): string {
  if (typeof utc !== "string" || !utc) return "";
  const when = new Date(utc);
  if (Number.isNaN(when.getTime())) return "";
  const part = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", ...options }).format(when);
  return `scheduled to leave ${part({ hour: "2-digit", minute: "2-digit", hour12: false })} on ${part({ day: "numeric", month: "short" })}`;
}

export function draftLinkText(item: TodayItem): string {
  const label = scheduledLabel(item.scheduled_utc);
  return label ? `Open draft, ${label}` : "Open draft";
}

export function safeLink(value: unknown): string | null {
  return typeof value === "string" && /^https:\/\//i.test(value) ? value : null;
}

export function showTodayBoard(query: string, listSource: string | null, hasSelection: boolean): boolean {
  return query.trim() === "" && listSource === null && !hasSelection;
}

export function isStepTile(section: string): boolean {
  return /^step_[3-7]$/.test(section);
}

export type TileLink = { kind: "draft" | "folder" | "portal"; label: string; url: string };

export function tileLink(item: TodayItem): TileLink | null {
  const raw = item.link as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== "object") return null;
  const url = safeLink(raw.url);
  const kind = raw.kind;
  if (!url || (kind !== "draft" && kind !== "folder" && kind !== "portal")) return null;
  return { kind, label: String(raw.label ?? "").trim() || (kind === "draft" ? "Open the draft" : kind === "folder" ? "Open the folder" : "Open the portal"), url };
}

export type StepAge = { current: string; days: number | null; quiet: boolean };

export function stepAge(item: TodayItem): StepAge | null {
  const raw = item.at_step as Record<string, unknown> | undefined;
  if (!raw || typeof raw !== "object") return null;
  const days = raw.days === null || raw.days === undefined || raw.days === "" ? null : Number(raw.days);
  return { current: String(raw.current ?? "").trim(), days: days !== null && Number.isFinite(days) ? days : null, quiet: raw.quiet === true };
}

export function stepLine(p: StepAge): string {
  const days = p.days === null ? "" : p.days === 0 ? "today" : p.days === 1 ? "1 day here" : `${p.days} days here`;
  return [p.current ? `now at ${p.current}` : "", days, p.quiet ? "quiet" : ""].filter(Boolean).join(" · ");
}

export function asOf(checkedUtc: unknown, now: Date = new Date()): string {
  const when = new Date(String(checkedUtc ?? ""));
  if (Number.isNaN(when.getTime())) return "";
  const day = (d: Date) => new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  if (day(when) === day(now)) return `as of ${new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit", hour12: false }).format(when)}`;
  return `as of ${new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", day: "numeric", month: "short" }).format(when)}`;
}
