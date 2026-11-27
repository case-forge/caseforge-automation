"use client";

import { useEffect, useState } from "react";
import { demoWindows } from "@/lib/demoWindows";

const TIME = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
const DATE = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Europe/London" });

export function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

export const IS_DEMO = process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1";

export function HeaderClock({ inMenu = false }: { inMenu?: boolean }) {
  const now = useNow();
  if (IS_DEMO) {
    return inMenu ? (
      <span className="app-drawer-item app-drawer-clock" aria-label="Demo">DEMO</span>
    ) : (
      <button type="button" className="cf-btn cf-btn--flush header-clock header-demo" data-header-measure="" aria-label="Show or hide the demo windows" title="Show or hide the demo windows" onClick={() => demoWindows.toggle()}>DEMO</button>
    );
  }
  if (!now) return null;
  const time = TIME.format(now);
  const date = DATE.format(now);
  if (inMenu) {
    return (
      <span className="app-drawer-item app-drawer-clock" aria-label={`${date}, ${time}`}>
        {time} &middot; {date}
      </span>
    );
  }
  return (
    <span className="header-clock" data-header-measure="" aria-label={`${date}, ${time}`}>
      <span className="header-clock-time">{time}</span>
      <span className="header-clock-date">{date}</span>
    </span>
  );
}
