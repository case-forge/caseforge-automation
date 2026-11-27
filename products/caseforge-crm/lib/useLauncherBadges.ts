"use client";

import { useEffect, useState } from "react";
import { useAutoSendData } from "./autoSendStore";
import { applyFilter, defaultFilter } from "./statusBoardFilter";
import { autoSendBadge, whatsNewTodayBadge, wetransferBadge } from "./launcherBadges";
import type { Badge } from "./launcherBadges";
import { useStatusBoardRows } from "./statusBoardRows";
import { fetchWhatsNew } from "./whatsNew";

export const BADGE_POLL_MS = 60_000;

export interface LauncherBadges {
  "status-board": Badge | null;
  "auto-sent": Badge | null;
  "whats-new": Badge | null;
}

const NONE: LauncherBadges = { "status-board": null, "auto-sent": null, "whats-new": null };

export function useLauncherBadges(): LauncherBadges {
  const [badges, setBadges] = useState<LauncherBadges>(NONE);

  const autoSend = useAutoSendData();

  const rows = useStatusBoardRows();
  useEffect(() => {
    let live = true;
    const set = (key: keyof LauncherBadges, badge: Badge | null) => live && setBadges((b) => ({ ...b, [key]: badge }));
    const refresh = () => {
      if (document.hidden) return;
      const now = new Date();
      void fetchWhatsNew()
        .then((data) => set("whats-new", whatsNewTodayBadge(data.items, now)))
        .catch(() => set("whats-new", null));
    };
    refresh();
    const timer = window.setInterval(refresh, BADGE_POLL_MS);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      live = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  return {
    ...badges,
    "status-board": rows ? wetransferBadge(applyFilter(rows, defaultFilter(rows).filter)) : null,
    "auto-sent": autoSend.status === "ready" ? autoSendBadge(autoSend.items) : null,
  };
}
