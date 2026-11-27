
import { HEADER_ITEMS } from "./headerOverflow";
import type { HeaderItemId } from "./headerOverflow";

export const CUSTOMISE_ITEMS = ["clients", "calendar", "flagged", "starred", "bell", "todo", "robot", "newclient", "clock"] as const;
export type CustomiseId = (typeof CUSTOMISE_ITEMS)[number];

export const CUSTOMISE_LABELS: Record<CustomiseId, string> = {
  clients: "Clients",
  calendar: "Calendar",
  flagged: "Flagged",
  starred: "Starred",
  bell: "Notifications",
  todo: "To do",
  robot: "Automation notices",
  newclient: "New client",
  clock: "Clock",
};

const KEY_PREFIX = "crm-header-hidden-v1";
export const LAST_USER_KEY = "crm-header-last-user-v1";

export function storageKeyFor(name: string): string | null {
  const who = name.trim().toLowerCase();
  return who ? `${KEY_PREFIX}:${who}` : null;
}

export function parseHidden(raw: string | null): CustomiseId[] {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return CUSTOMISE_ITEMS.filter((id) => value.includes(id));
  } catch {
    return [];
  }
}

export function serialiseHidden(hidden: readonly CustomiseId[]): string {
  return JSON.stringify(CUSTOMISE_ITEMS.filter((id) => hidden.includes(id)));
}

export function toggleHidden(hidden: readonly CustomiseId[], id: CustomiseId): CustomiseId[] {
  const next = hidden.includes(id) ? hidden.filter((h) => h !== id) : [...hidden, id];
  return CUSTOMISE_ITEMS.filter((c) => next.includes(c));
}

export function hiddenHeaderItems(hidden: readonly CustomiseId[]): HeaderItemId[] {
  return HEADER_ITEMS.filter((id) => {
    if (id === "view") return hidden.includes("clients") && hidden.includes("calendar");
    return (hidden as readonly string[]).includes(id);
  });
}

export const ALL_HIDDEN: readonly CustomiseId[] = CUSTOMISE_ITEMS;
