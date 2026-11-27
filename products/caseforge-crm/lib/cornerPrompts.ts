"use client";

import { useSyncExternalStore } from "react";
import { useEffect, useRef } from "react";
import { windowPins } from "./windowPins";
import { popupStack } from "./popupStack";

const WINDOW_IDS: Partial<Record<CornerId, string>> = { "whats-new": "whats-new", classifier: "classifier-prompt" };

export type CornerId = "whats-new" | "classifier" | "hearings" | "add-hearing";

const STACK_IDS: Record<CornerId, string> = { "whats-new": "whats-new", classifier: "classifier-prompt", hearings: "hearings-rail", "add-hearing": "add-hearing" };

const showing = new Set<CornerId>();
const closeRequests: Record<CornerId, number> = { "whats-new": 0, classifier: 0, hearings: 0, "add-hearing": 0 };
const closeHandled: Record<CornerId, number> = { "whats-new": 0, classifier: 0, hearings: 0, "add-hearing": 0 };

const counters: Record<CornerId, number> = { "whats-new": 0, classifier: 0, hearings: 0, "add-hearing": 0 };
const handled: Record<CornerId, number> = { "whats-new": 0, classifier: 0, hearings: 0, "add-hearing": 0 };
const closed = new Set<CornerId>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export function requestOpen(id: CornerId): void {
  closed.delete(id);
  const windowId = WINDOW_IDS[id];
  if (windowId) windowPins.bringForward(windowId);
  popupStack.raise(STACK_IDS[id]);
  counters[id] += 1;
  emit();
}

export function consumeRequest(id: CornerId): boolean {
  if (counters[id] <= handled[id]) return false;
  handled[id] = counters[id];
  return true;
}

export function markClosed(id: CornerId): void {
  closed.add(id);
}

export function isClosed(id: CornerId): boolean {
  return closed.has(id);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useOpenRequests(id: CornerId): number {
  return useSyncExternalStore(subscribe, () => counters[id], () => 0);
}

export function toggleDecision(isShowing: boolean): "close" | "open" {
  return isShowing ? "close" : "open";
}

export function toggleWindow(id: CornerId): void {
  if (toggleDecision(showing.has(id)) === "close") {
    closeRequests[id] += 1;
    emit();
    return;
  }
  requestOpen(id);
}

export function reportShowing(id: CornerId, isShowing: boolean): void {
  if (isShowing === showing.has(id)) return;
  if (isShowing) showing.add(id);
  else showing.delete(id);
  emit();
}

export function clearShowing(id: CornerId): void {
  if (showing.delete(id)) emit();
}

export function consumeCloseRequest(id: CornerId): boolean {
  if (closeRequests[id] <= closeHandled[id]) return false;
  closeHandled[id] = closeRequests[id];
  return true;
}

export function useReportShowing(id: CornerId, isShowing: boolean, close: () => void): void {
  const latest = useRef(close);
  useEffect(() => {
    latest.current = close;
  });
  useEffect(() => reportShowing(id, isShowing));
  const asked = useSyncExternalStore(subscribe, () => closeRequests[id], () => 0);
  useEffect(() => {
    if (consumeCloseRequest(id)) latest.current();
  }, [asked, id]);
  useEffect(() => () => clearShowing(id), [id]);
}

export function useWindowShowing(id: CornerId): boolean {
  return useSyncExternalStore(subscribe, () => showing.has(id), () => false);
}
