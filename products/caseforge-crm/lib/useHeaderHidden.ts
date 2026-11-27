"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useSignedInName } from "./editorName";
import { ALL_HIDDEN, LAST_USER_KEY, parseHidden, serialiseHidden, storageKeyFor } from "./headerCustomise";
import { toggleHidden } from "./headerCustomise";
import type { CustomiseId } from "./headerCustomise";

const NONE: readonly CustomiseId[] = [];
const listeners = new Set<() => void>();

const memory = new Map<string, string>();
let snapshotKey = "";
let snapshotRaw: string | null = null;
let snapshot: readonly CustomiseId[] = NONE;

function readRaw(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function read(name: string): readonly CustomiseId[] {
  const key = storageKeyFor(name);
  if (!key) return NONE;
  const raw = memory.get(key) ?? readRaw(key);
  if (key !== snapshotKey || raw !== snapshotRaw) {
    snapshotKey = key;
    snapshotRaw = raw;
    snapshot = parseHidden(raw);
  }
  return snapshot;
}

function lastUser(): string {
  try {
    return window.localStorage.getItem(LAST_USER_KEY) ?? "";
  } catch {
    return "";
  }
}

export function useHeaderHidden(): { hidden: readonly CustomiseId[]; toggle: (id: CustomiseId) => void; showAll: () => void; hideAll: () => void } {
  const signedIn = useSignedInName();
  const subscribe = useCallback((onChange: () => void) => {
    listeners.add(onChange);
    window.addEventListener("storage", onChange);
    return () => {
      listeners.delete(onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  const hidden = useSyncExternalStore(
    subscribe,
    () => read(signedIn || lastUser()),
    () => NONE,
  );

  useEffect(() => {
    if (!signedIn) return;
    try {
      window.localStorage.setItem(LAST_USER_KEY, signedIn);
    } catch {

    }
  }, [signedIn]);

  const write = (next: readonly CustomiseId[]) => {
    const key = storageKeyFor(signedIn || lastUser());
    if (!key) return;
    const raw = serialiseHidden(next);
    memory.set(key, raw);
    try {
      window.localStorage.setItem(key, raw);
    } catch {

    }
    for (const listener of listeners) listener();
  };

  return { hidden, toggle: (id) => write(toggleHidden(hidden, id)), showAll: () => write([]), hideAll: () => write(ALL_HIDDEN) };
}
