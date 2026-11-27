"use client";

import { useSyncExternalStore } from "react";
import { normaliseTime } from "./hearings";
import type { HearingFormValues } from "./hearings";

export interface HearingDraft {
  id: string;
  savedAt: string;

  matterId: string;
  clientName?: string;

  values: Partial<HearingFormValues>;
}

const KEY = "caseforge-client-viewer:hearing-drafts";
export const MAX_HEARING_DRAFTS = 60;

function readRaw(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

function parse(raw: string): HearingDraft[] {
  if (!raw) return [];
  try {
    const list = JSON.parse(raw) as unknown;
    if (!Array.isArray(list)) return [];
    return list.filter((d): d is HearingDraft => !!d && typeof (d as HearingDraft).id === "string" && typeof (d as HearingDraft).values === "object");
  } catch {
    return [];
  }
}

function writeList(list: HearingDraft[]): void {
  if (typeof window === "undefined") return;
  try {
    if (list.length === 0) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX_HEARING_DRAFTS)));
  } catch {

  }
  emit();
}

const listeners = new Set<() => void>();
function emit() {
  listeners.forEach((l) => l());
}

export function loadHearingDrafts(): HearingDraft[] {
  return parse(readRaw());
}

export function hasDraftContent(values: Partial<HearingFormValues>): boolean {
  return Object.entries(values).some(([key, value]) => key !== "matter_id" && (typeof value === "boolean" ? value : String(value ?? "").trim() !== ""));
}

export function saveHearingDraft(input: { id?: string; matterId: string; clientName?: string; values: Partial<HearingFormValues> }, now: Date = new Date()): HearingDraft {
  const draft: HearingDraft = {
    id: input.id || `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
    savedAt: now.toISOString(),
    matterId: input.matterId,
    ...(input.clientName ? { clientName: input.clientName } : {}),
    values: input.values,
  };
  writeList([draft, ...loadHearingDrafts().filter((d) => d.id !== draft.id)]);
  return draft;
}

export function deleteHearingDraft(id: string): void {
  const before = loadHearingDrafts();
  const next = before.filter((d) => d.id !== id);
  if (next.length !== before.length) writeList(next);
}

export function draftsForMatter(drafts: HearingDraft[], matterId: string): HearingDraft[] {
  return drafts.filter((d) => d.matterId === matterId);
}

export function datedDraftsBetween(drafts: HearingDraft[], from: string, toExclusive?: string): HearingDraft[] {
  return drafts.filter((d) => {
    const date = String(d.values.hearing_date ?? "").slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= from && (!toExclusive || date < toExclusive);
  });
}

export function draftLabel(d: HearingDraft): string {
  return d.clientName?.trim() || String(d.values.case_ref ?? "").trim() || "Hearing draft";
}

export function draftEvent(draft: HearingDraft) {
  const date = String(draft.values.hearing_date ?? "").slice(0, 10);
  const time = normaliseTime(String(draft.values.hearing_time ?? ""));
  return {
    id: `draft-${draft.id}`,
    title: `DRAFT - ${draftLabel(draft)}`,
    start: time ? `${date}T${time}:00` : date,
    allDay: time === null,
    classNames: ["hearing-ev", "hearing-ev--draft"],
    extendedProps: { draft },
  };
}

let cachedRaw: string | null = null;
let cached: HearingDraft[] = [];
function snapshot(): HearingDraft[] {
  const raw = readRaw();
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cached = parse(raw);
  }
  return cached;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY || e.key === null) listener();
  };
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
  };
}

const EMPTY: HearingDraft[] = [];

export function useHearingDrafts(): HearingDraft[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY);
}
