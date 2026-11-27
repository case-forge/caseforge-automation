"use client";

import { useEffect, useState } from "react";
import { IconMoon, IconSun, IconSystem } from "./icons";

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "caseforge-client-viewer:theme";

const CYCLE: Array<{ value: ThemeChoice; label: string; icon: React.ReactNode }> = [
  { value: "light", label: "Light", icon: <IconSun /> },
  { value: "dark", label: "Dark", icon: <IconMoon /> },
  { value: "system", label: "Auto", icon: <IconSystem /> },
];

export function readStoredTheme(raw: string | null): ThemeChoice {
  return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>("system");

  useEffect(() => {
    try {
      setChoice(readStoredTheme(window.localStorage.getItem(THEME_STORAGE_KEY)));
    } catch {

    }
  }, []);

  function choose(next: ThemeChoice) {
    setChoice(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {

    }
  }

  const index = Math.max(0, CYCLE.findIndex((c) => c.value === choice));
  const current = CYCLE[index];
  const next = CYCLE[(index + 1) % CYCLE.length];

  return (
    <button
      type="button"
      className="cf-btn cf-btn--flush app-drawer-quick-list-item theme-toggle"
      aria-label={`Theme: ${current.label}. Switch to ${next.label}`}
      title={`Switch to ${next.label}`}
      onClick={() => choose(next.value)}
    >
      {current.icon}
      <span>Theme: {current.label}</span>
    </button>
  );
}
