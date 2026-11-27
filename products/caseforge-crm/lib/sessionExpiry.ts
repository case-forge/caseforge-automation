
import { useEffect, useState } from "react";

export const COUNTDOWN_MS = 5 * 60_000;

type Listener = (expiresAt: number | null) => void;

let current: number | null = null;
const listeners = new Set<Listener>();

export function reportSessionExpiry(expiresAt: number | null): void {
  current = expiresAt;
  listeners.forEach((listener) => listener(expiresAt));
}

export function countdownLabel(expiresAt: number | null, now: number): string | null {
  if (expiresAt === null) return null;
  const remaining = expiresAt - now;
  if (remaining <= 0 || remaining > COUNTDOWN_MS) return null;
  const seconds = Math.ceil(remaining / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function useSessionCountdown(): string | null {
  const [expiresAt, setExpiresAt] = useState<number | null>(current);
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    listeners.add(setExpiresAt);
    setExpiresAt(current);
    return () => {
      listeners.delete(setExpiresAt);
    };
  }, []);

  useEffect(() => {
    if (expiresAt === null) return;

    const untilWindow = expiresAt - Date.now() - COUNTDOWN_MS;
    let timer = 0;
    const startTicking = () => {
      setNow(Date.now());
      timer = window.setInterval(() => setNow(Date.now()), 1000);
    };
    const wait = untilWindow > 0 ? window.setTimeout(startTicking, untilWindow) : (startTicking(), 0);
    return () => {
      window.clearTimeout(wait);
      window.clearInterval(timer);
    };
  }, [expiresAt]);

  return countdownLabel(expiresAt, now);
}
