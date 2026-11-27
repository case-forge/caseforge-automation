
import { WAITING_LISTS } from "./waiting";

export type FlagListId = string;
export type ClientListId = "to-check" | "concluded" | FlagListId;

export interface ClientListDef {
  id: ClientListId;

  label: string;

  flag?: string;
}

export const CLIENT_LISTS: ClientListDef[] = [
  { id: "to-check", label: "To check" },
  { id: "concluded", label: "Concluded" },
  { id: "flagged", label: "Flagged", flag: "flagged" },
  { id: "starred", label: "Starred", flag: "starred" },

  { id: "frequent-callers", label: "Frequent callers", flag: "persistent_caller,persistent_caller_respondent" },
  { id: "transferred", label: "Transferred", flag: "transferred" },
  { id: "dropped-out", label: "Dropped out", flag: "dropped_out" },
  { id: "billed", label: "Billed", flag: "billed" },

  { id: "private", label: "Private", flag: "src_private" },

  { id: "duplicates", label: "Duplicates" },
  { id: "removed", label: "Removed" },
  { id: "merged", label: "Merged" },

  ...WAITING_LISTS.map(({ flag, label }) => ({ id: flag.replace(/_/g, "-"), label, flag })),
];

export function listFromParam(value: string | null): ClientListId {
  return CLIENT_LISTS.find((l) => l.id === value)?.id ?? "to-check";
}

export function listHref(id: ClientListId): string {
  return id === "to-check" ? "/client-lists" : `/client-lists?list=${id}`;
}
