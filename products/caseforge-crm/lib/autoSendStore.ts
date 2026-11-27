"use client";

import { useSyncExternalStore } from "react";
import { parseResponse } from "./autoSend";
import type { AutoSendItem } from "./autoSend";

export const LEAVING_SOON_REFRESH_MS = 30_000;

export function refreshDelay(i: { hasLeavingSoon: boolean; visible: boolean; opened: boolean }): number | null {
  if (!i.visible) return null;
  if (i.opened) return 0;
  return i.hasLeavingSoon ? LEAVING_SOON_REFRESH_MS : null;
}

export type AutoSendLoad = { status: "loading" } | { status: "unavailable" } | { status: "failed" } | { status: "ready"; items: AutoSendItem[] };

let state: AutoSendLoad = { status: "loading" };
let started = false;
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight: AbortController | null = null;
const listeners = new Set<() => void>();

const isVisible = (): boolean => typeof document === "undefined" || !document.hidden;
const hasLeavingSoon = (): boolean => state.status === "ready" && state.items.some((i) => i.state === "leaving_soon" && !i.dismissed);

function set(next: AutoSendLoad) {
  state = next;
  listeners.forEach((l) => l());
}

function schedule() {
  if (timer) clearTimeout(timer);
  timer = null;
  const delay = refreshDelay({ hasLeavingSoon: hasLeavingSoon(), visible: isVisible(), opened: false });
  if (delay !== null) timer = setTimeout(() => void refreshAutoSend(), delay);
}

export async function refreshAutoSend(): Promise<void> {
  inFlight?.abort();
  const ctl = new AbortController();
  inFlight = ctl;
  try {
    const res = await fetch("/api/auto-send", { cache: "no-store", signal: ctl.signal });
    if (res.status === 404 || res.status === 405 || res.status === 501) set({ status: "unavailable" });
    else if (!res.ok) set(state.status === "ready" ? state : { status: "failed" });
    else set({ status: "ready", items: parseResponse(await res.json()) });
  } catch {
    if (!ctl.signal.aborted) set(state.status === "ready" ? state : { status: "failed" });
  }
  if (!ctl.signal.aborted) schedule();
}

export function onAutoSendOpened(): void {
  if (isVisible()) void refreshAutoSend();
}

export function onIntakeSignal(): void {
  void refreshAutoSend();
}

function start() {
  if (started || typeof document === "undefined") return;
  started = true;
  document.addEventListener("visibilitychange", () => {
    if (isVisible()) void refreshAutoSend();
    else if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  });
  void refreshAutoSend();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  start();
  return () => {
    listeners.delete(listener);
  };
}

export function useAutoSendData(): AutoSendLoad {
  return useSyncExternalStore(subscribe, () => state, () => ({ status: "loading" }) as AutoSendLoad);
}
