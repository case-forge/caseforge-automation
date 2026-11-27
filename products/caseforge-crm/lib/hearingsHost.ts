"use client";

import { useSyncExternalStore } from "react";
import { clientHref } from "./clientLink";
import { requestOpen } from "./cornerPrompts";
import { TABS_FULL_HINT, activateTab, addTab, closeTab, emptyTabs, parseTabs, serialiseTabs } from "./hearingTabs";
import type { HearingTab, TabsState } from "./hearingTabs";
import { hearingToast } from "./hearingToast";
import type { HearingDraft } from "./hearingDrafts";
import type { Hearing, HearingFormValues } from "./hearings";

let version = 0;
let reviewCount = 0;
let upcomingCount = 0;

export interface CreateSpec {

  matterId: string;

  suffix?: string;
  clientName?: string;
  defaults: Partial<HearingFormValues>;
  known?: Hearing[];
  intro?: string;

  onCreated?: (hearing: Hearing) => void;

  openAfter?: boolean;

  draftId?: string;

  restoreValues?: Partial<HearingFormValues>;
}

export type DrawerEntry =
  | { key: string; kind: "edit"; hearing: Hearing; startEditing: boolean }
  | { key: string; kind: "create"; spec: CreateSpec };

export const editKey = (hearing: Pick<Hearing, "hearing_id">): string => `hearing-edit-${hearing.hearing_id}`;
export const createKey = (spec: Pick<CreateSpec, "matterId" | "suffix"> & { draftId?: string }): string =>
  `hearing-new:${spec.draftId ? `draft-${spec.draftId}` : spec.matterId || spec.suffix || "none"}`;

export function addDrawer(list: DrawerEntry[], entry: DrawerEntry): { list: DrawerEntry[]; existed: boolean } {
  const current = list[0];
  if (!current || current.key !== entry.key) return { list: [entry], existed: false };
  if (entry.kind === "edit" && current.kind === "edit") {
    return { list: [{ ...entry, startEditing: current.startEditing || entry.startEditing }], existed: true };
  }
  return { list, existed: true };
}

export function removeDrawer(list: DrawerEntry[], key: string): DrawerEntry[] {
  return list.some((d) => d.key === key) ? list.filter((d) => d.key !== key) : list;
}

export function updateEditDrawer(list: DrawerEntry[], hearing: Hearing): DrawerEntry[] {
  return list.map((d) => (d.kind === "edit" && d.hearing.hearing_id === hearing.hearing_id ? { ...d, hearing } : d));
}

let drawers: DrawerEntry[] = [];

let tabs: TabsState<CreateSpec> = emptyTabs();
let tabsLoaded = false;
let blankCount = 0;
export const TABS_STORAGE_KEY = "caseforge-client-viewer:add-hearing-tabs-v1";
function loadTabs() {
  if (tabsLoaded || typeof window === "undefined") return;
  tabsLoaded = true;
  try {
    tabs = parseTabs<CreateSpec>(window.sessionStorage.getItem(TABS_STORAGE_KEY));
  } catch {
    tabs = emptyTabs();
  }
}
function saveTabs() {
  try {
    window.sessionStorage.setItem(TABS_STORAGE_KEY, serialiseTabs(tabs as TabsState<object>));
  } catch {

  }
}

const guards = new Map<string, () => boolean>();
let openClient: ((hearing: Hearing) => void) | null = null;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

let openAttempts = 0;

function release(): boolean {
  const current = drawers[0];
  if (!current) return true;
  const guard = guards.get(current.key);
  return guard ? guard() : true;
}

export const hearingsHost = {

  openEdit(hearing: Hearing, opts?: { startEditing?: boolean }) {
    openAttempts += 1;
    const key = editKey(hearing);
    if (drawers[0] && drawers[0].key !== key && !release()) return;
    drawers = addDrawer(drawers, { key, kind: "edit", hearing, startEditing: !!opts?.startEditing }).list;
    emit();
  },

  openCreate(spec: CreateSpec) {
    openAttempts += 1;
    loadTabs();
    const added = addTab(tabs, { key: createKey(spec), spec });
    if (added.full) {
      hearingToast.show(TABS_FULL_HINT);
      return;
    }
    tabs = added.state;
    saveTabs();
    requestOpen("add-hearing");
    emit();
  },

  addBlankTab(): boolean {
    loadTabs();
    blankCount += 1;
    const before = tabs;
    this.openCreate({ matterId: "", suffix: `blank-${Date.now().toString(36)}-${blankCount}`, defaults: {} });
    return tabs !== before;
  },

  tabs: (): TabsState<CreateSpec> => {
    loadTabs();
    return tabs;
  },
  showTab(key: string) {
    tabs = activateTab(tabs, key);
    saveTabs();
    emit();
  },

  closeTabNow(key: string) {
    loadTabs();
    guards.delete(key);
    tabs = closeTab(tabs, key);
    saveTabs();
    emit();
  },

  requestCloseTab(key: string): boolean {
    const guard = guards.get(key);
    if (guard && !guard()) return false;
    this.closeTabNow(key);
    return true;
  },

  openDraft(draft: HearingDraft, known?: Hearing[]) {
    this.openCreate({
      matterId: draft.matterId,
      clientName: draft.clientName,
      defaults: draft.matterId ? { matter_id: draft.matterId } : {},
      restoreValues: draft.values,
      draftId: draft.id,
      known,
    });
  },

  drawers: (): DrawerEntry[] => drawers,

  openAttempts: (): number => openAttempts,

  closeDrawer(key: string) {
    if (tabs.tabs.some((t) => t.key === key)) {
      this.closeTabNow(key);
      return;
    }
    drawers = removeDrawer(drawers, key);
    emit();
  },

  requestClose(): boolean {
    if (drawers.length === 0) return true;
    if (!release()) return false;
    drawers = [];
    emit();
    return true;
  },

  registerGuard(key: string, guard: () => boolean) {
    guards.set(key, guard);
    return () => {
      if (guards.get(key) === guard) guards.delete(key);
    };
  },
  updateEdit(hearing: Hearing) {
    drawers = updateEditDrawer(drawers, hearing);
    emit();
  },

  bump() {
    version += 1;
    emit();
  },

  setUpcomingCount(next: number) {
    if (next === upcomingCount) return;
    upcomingCount = next;
    emit();
  },
  setReviewCount(next: number) {
    if (next === reviewCount) return;
    reviewCount = next;
    emit();
  },

  register(handler: (hearing: Hearing) => void) {
    openClient = handler;
    return () => {
      if (openClient === handler) openClient = null;
    };
  },

  openInWorkspace(hearing: Hearing): boolean {
    if (!openClient) return false;
    openClient(hearing);
    return true;
  },
};

export function hearingHref(hearing: Hearing): string {
  const key = hearing.case_ref.trim() || (hearing.client_name ?? "").trim();
  if (!key) return "/";
  if (hearing.matter_id != null) return clientHref(key, { matterId: String(hearing.matter_id), tab: "hearings", hearingId: hearing.hearing_id });
  return clientHref(key);
}

export function useHearingsVersion(): number {
  return useSyncExternalStore(subscribe, () => version, () => 0);
}

export function useHearingTabs(): TabsState<CreateSpec> {
  return useSyncExternalStore(
    subscribe,
    () => hearingsHost.tabs(),
    () => emptyTabs<CreateSpec>(),
  );
}
export type { HearingTab };

let drawerSnapshot: DrawerEntry[] = [];
export function useHearingDrawers(): DrawerEntry[] {
  return useSyncExternalStore(
    subscribe,
    () => {
      if (drawerSnapshot !== drawers) drawerSnapshot = drawers;
      return drawerSnapshot;
    },
    () => [],
  );
}

export function useHearingsUpcomingCount(): number {
  return useSyncExternalStore(subscribe, () => upcomingCount, () => 0);
}

export function countBadge(count: number): string {
  return count > 0 ? String(count) : "";
}

export function useHearingsReviewCount(): number {
  return useSyncExternalStore(subscribe, () => reviewCount, () => 0);
}
