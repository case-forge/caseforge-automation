"use client";

import { useCallback, useSyncExternalStore } from "react";

export const CLASSIFIER_PROMPTS_STORAGE_KEY = "caseforge-client-viewer:classifier-prompts";

const listeners = new Set<() => void>();

export function readStoredClassifierPrompts(raw: string | null): boolean {
  return raw === "on";
}

export function classifierPromptsOn(): boolean {
  try {
    return readStoredClassifierPrompts(window.localStorage.getItem(CLASSIFIER_PROMPTS_STORAGE_KEY));
  } catch {
    return false;
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function useClassifierPrompts(): [boolean, (next: boolean) => void] {
  const on = useSyncExternalStore(subscribe, classifierPromptsOn, () => false);
  const set = useCallback((next: boolean) => {
    try {
      window.localStorage.setItem(CLASSIFIER_PROMPTS_STORAGE_KEY, next ? "on" : "off");
    } catch {

    }
    listeners.forEach((l) => l());
  }, []);
  return [on, set];
}
