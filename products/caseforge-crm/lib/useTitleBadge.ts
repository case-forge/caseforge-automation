"use client";

import { useEffect } from "react";
import { badgedTitle } from "./tabTitle";

export function useTitleBadge(unread: number): void {
  useEffect(() => {
    const apply = () => {
      const next = badgedTitle(document.title, unread);
      if (next !== document.title) document.title = next;
    };
    apply();
    const el = document.querySelector("title");
    if (!el || typeof MutationObserver === "undefined") return;
    const watcher = new MutationObserver(apply);
    watcher.observe(el, { childList: true, characterData: true, subtree: true });
    return () => {
      watcher.disconnect();
      document.title = badgedTitle(document.title, 0);
    };
  }, [unread]);
}
