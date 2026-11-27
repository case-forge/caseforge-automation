
import type { ComponentType, SVGProps } from "react";
import { IconAutomation, IconBoard, IconCalendar, IconClock } from "@/components/icons";
import { clientHref } from "./clientLink";
import { applyFilter, defaultFilter } from "./statusBoardFilter";
import { boardRows } from "./boardCompact";
import type { StatusBoardResponse } from "./matterMilestones";

export interface TeaserSummary {

  stats: { label: string; value: number }[];

  listTitle: string;
  links: { label: string; href: string }[];

  note: string;

  rows?: StatusBoardResponse["items"];
}

export interface Teaser {
  id: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;

  href: string;
  available: boolean;

  load: () => Promise<TeaserSummary>;
}

export const FAILURE_LINE = "This overview could not be loaded.";

type Row = StatusBoardResponse["items"][number];

export function summariseStatusBoard(items: Row[], now: Date = new Date()): TeaserSummary {
  const { filter, fallback } = defaultFilter(items);
  const shown = applyFilter(items, filter);
  const newest = shown
    .filter((i) => i.date_joined)
    .sort((a, b) => b.date_joined.localeCompare(a.date_joined))
    .slice(0, 3);
  return {
    stats: [
      { label: "Matters shown", value: shown.length },
      { label: "No contacted time", value: shown.filter((i) => !i.milestones?.contacted).length },
      { label: "No filed time", value: shown.filter((i) => !i.milestones?.filed).length },
    ],
    listTitle: "Most recently joined",
    links: newest.map((i) => ({ label: i.client_name, href: clientHref(i.client_name, { matterId: i.matter_id }) })),
    rows: boardRows(shown, now),
    note: fallback ? "No NMO-CAO folder found, so all open matters are counted." : "NMO and CAO matters in the NMO-CAO folder.",
  };
}

async function loadStatusBoard(): Promise<TeaserSummary> {
  const res = await fetch("/api/status-board", { cache: "no-store" });
  if (!res.ok) throw new Error("status board");
  const body = (await res.json()) as StatusBoardResponse;
  return summariseStatusBoard(Array.isArray(body.items) ? body.items : []);
}

export const TEASERS: Teaser[] = [
  { id: "status-board", label: "Status Board", icon: IconBoard, href: "/status-board", available: true, load: loadStatusBoard },

  {
    id: "auto-sent",
    label: "Auto Send",
    icon: IconClock,
    href: "/",
    available: true,
    load: () => Promise.resolve({ stats: [], listTitle: "", links: [], note: "" }),
  },

  {
    id: "court-prep",
    label: "Court Prep",
    icon: IconCalendar,
    href: "/court-prep",
    available: true,
    load: () => Promise.resolve({ stats: [], listTitle: "", links: [], note: "" }),
  },

  {
    id: "producer",
    label: "Producer",
    icon: IconAutomation,
    href: "/",
    available: false,
    load: () => Promise.reject(new Error("The Producer teaser is not available.")),
  },
];

export function availableTeasers(list: Teaser[] = TEASERS): Teaser[] {
  return list.filter((t) => t.available);
}

export function findTeaser(id: string, list: Teaser[] = TEASERS): Teaser | undefined {
  return list.find((t) => t.id === id);
}

export const STORAGE_KEY = "front-page-teasers-v1";

export interface TeaserChoice {
  hidden: string[];
  open: string;
}

export const DEFAULT_CHOICE: TeaserChoice = { hidden: [], open: "" };

export function parseChoice(raw: string | null): TeaserChoice {
  if (!raw) return DEFAULT_CHOICE;
  try {
    const data = JSON.parse(raw) as { hidden?: unknown; open?: unknown };
    const hidden = Array.isArray(data.hidden) ? data.hidden.filter((h): h is string => typeof h === "string") : [];
    return { hidden, open: typeof data.open === "string" ? data.open : "" };
  } catch {
    return DEFAULT_CHOICE;
  }
}

export function serialiseChoice(choice: TeaserChoice): string {
  return JSON.stringify({ hidden: choice.hidden, open: choice.open });
}

export function visibleTeasers(choice: TeaserChoice, list: Teaser[] = TEASERS): Teaser[] {
  return availableTeasers(list).filter((t) => !choice.hidden.includes(t.id));
}

export function openId(choice: TeaserChoice, list: Teaser[] = TEASERS): string {
  return visibleTeasers(choice, list).some((t) => t.id === choice.open) ? choice.open : "";
}

export function toggleOpen(choice: TeaserChoice, id: string): TeaserChoice {
  return { ...choice, open: choice.open === id ? "" : id };
}

export function toggleShown(choice: TeaserChoice, id: string): TeaserChoice {
  const hidden = choice.hidden.includes(id) ? choice.hidden.filter((h) => h !== id) : [...choice.hidden, id];
  return { hidden, open: hidden.includes(choice.open) ? "" : choice.open };
}
