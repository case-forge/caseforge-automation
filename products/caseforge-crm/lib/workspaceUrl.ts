
export type CalendarMode = "month" | "week" | "agenda";

export type WorkspaceRoute =
  | { kind: "home" }
  | { kind: "clients" }
  | { kind: "client"; matterId: string; tab: string | null }
  | { kind: "calendar"; date: string | null; mode: CalendarMode | null };

const MODES: readonly CalendarMode[] = ["month", "week", "agenda"];
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const DAY = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

export function parseWorkspacePath(pathname: string): WorkspaceRoute {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "calendar") {
    const date = parts[1] && (MONTH.test(parts[1]) || DAY.test(parts[1])) ? parts[1] : null;
    const mode = (MODES as readonly string[]).includes(parts[2] ?? "") ? (parts[2] as CalendarMode) : null;
    return { kind: "calendar", date, mode };
  }
  if (parts[0] === "clients") {
    if (parts[1] && /^\d+$/.test(parts[1])) return { kind: "client", matterId: parts[1], tab: parts[2] ?? null };
    return { kind: "clients" };
  }
  return { kind: "home" };
}

export function calendarPath(anchor: string, mode: CalendarMode): string {
  const day = anchor.slice(0, 10);
  if (mode === "week") return `/calendar/${day}/week`;
  return mode === "agenda" ? `/calendar/${day.slice(0, 7)}/agenda` : `/calendar/${day.slice(0, 7)}`;
}

export function clientPath(matterId: string, tab: string | null, name: string): string {
  const base = `/clients/${encodeURIComponent(matterId)}${tab ? `/${encodeURIComponent(tab)}` : ""}`;
  return name.trim() ? `${base}?q=${encodeURIComponent(name.trim())}` : base;
}

export function searchPath(query: string): string {
  return query.trim().length >= 2 ? `/clients?q=${encodeURIComponent(query.trim())}` : "/";
}

export const MODE_TO_VIEW: Record<CalendarMode, "dayGridMonth" | "timeGridWeek" | "listMonth"> = {
  month: "dayGridMonth",
  week: "timeGridWeek",
  agenda: "listMonth",
};
export function viewToMode(view: string): CalendarMode {
  return view === "timeGridWeek" ? "week" : view === "listMonth" ? "agenda" : "month";
}
