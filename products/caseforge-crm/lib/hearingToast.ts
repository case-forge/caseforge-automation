"use client";

import { useSyncExternalStore } from "react";

export interface HearingToast {
  id: number;
  message: string;
}

let current: HearingToast | null = null;
let counter = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const hearingToast = {
  show(message: string): void {
    counter += 1;
    current = { id: counter, message };
    emit();
  },
  dismiss(id?: number): void {
    if (current && (id === undefined || current.id === id)) {
      current = null;
      emit();
    }
  },
};

export function useHearingToast(): HearingToast | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
    () => current,
    () => null,
  );
}
