"use client";

import { useEffect } from "react";
import { REFRESH_CHECK_MS, shouldRefresh } from "../lib/scheduledRefresh";
import { reloadKeepingDrafts, unsavedSources } from "../lib/unsavedEdits";

const ACTIVITY_EVENTS = ["keydown", "pointerdown", "pointermove", "wheel", "touchstart"] as const;

async function serverBuildId(): Promise<string | null> {
  try {
    const res = await fetch("/api/version", { cache: "no-store", redirect: "manual" });
    if (!res.ok) return null;
    const body = (await res.json()) as { buildId?: unknown };
    return typeof body.buildId === "string" && body.buildId ? body.buildId : null;
  } catch {
    return null;
  }
}

export function ScheduledRefresh() {
  useEffect(() => {
    const loadedAt = Date.now();
    let lastActive = Date.now();
    let loadedBuild: string | null = null;
    let checking = false;

    const touch = () => {
      lastActive = Date.now();
    };
    for (const name of ACTIVITY_EVENTS) window.addEventListener(name, touch, { passive: true });

    void serverBuildId().then((id) => {
      loadedBuild = id;
    });

    const timer = window.setInterval(async () => {
      if (checking) return;
      checking = true;
      try {
        const idleMs = Date.now() - lastActive;
        const unsaved = unsavedSources().length;

        const probe = shouldRefresh({ ageMs: Date.now() - loadedAt, idleMs, unsaved, newBuild: true });
        if (!probe) return;
        const current = await serverBuildId();
        if (loadedBuild === null) loadedBuild = current;
        const newBuild = current !== null && loadedBuild !== null && current !== loadedBuild;
        if (shouldRefresh({ ageMs: Date.now() - loadedAt, idleMs: Date.now() - lastActive, unsaved: unsavedSources().length, newBuild })) {
          reloadKeepingDrafts();
        }
      } finally {
        checking = false;
      }
    }, REFRESH_CHECK_MS);

    return () => {
      window.clearInterval(timer);
      for (const name of ACTIVITY_EVENTS) window.removeEventListener(name, touch);
    };
  }, []);
  return null;
}
