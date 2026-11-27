"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { hearingsHost } from "@/lib/hearingsHost";
import { hearingToast, useHearingToast } from "@/lib/hearingToast";

const KEEP_OPEN = ".hearing-slideout, .hearing-toast, .app-header, .fw, [role=\"dialog\"], [role=\"menu\"], [role=\"listbox\"]";

export function shouldCloseOnClick(c: { attemptsBefore: number; attemptsNow: number; connected: boolean; insideKept: boolean; eventTime: number; mountedAt: number }): boolean {
  if (c.attemptsNow !== c.attemptsBefore) return false;
  if (!c.connected || c.insideKept) return false;
  return c.eventTime > c.mountedAt;
}

export function HearingSlideOut({ children }: { children: ReactNode }) {
  useEffect(() => {
    const mountedAt = performance.now();
    let attemptsBefore = hearingsHost.openAttempts();

    const first = () => {
      attemptsBefore = hearingsHost.openAttempts();
    };
    const last = (e: MouseEvent) => {
      const target = e.target instanceof Element ? e.target : null;
      if (
        shouldCloseOnClick({
          attemptsBefore,
          attemptsNow: hearingsHost.openAttempts(),
          connected: !!target && target.isConnected,
          insideKept: !!target?.closest(KEEP_OPEN),
          eventTime: e.timeStamp,
          mountedAt,
        })
      ) {
        hearingsHost.requestClose();
      }
    };
    document.addEventListener("click", first, true);
    document.addEventListener("click", last, false);
    return () => {
      document.removeEventListener("click", first, true);
      document.removeEventListener("click", last, false);
    };
  }, []);
  return createPortal(
    <aside className="hearing-slideout" aria-label="Hearing">
      {children}
    </aside>,
    document.body,
  );
}

export function HearingToaster() {
  const toast = useHearingToast();
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => hearingToast.dismiss(toast.id), 7000);
    return () => window.clearTimeout(timer);
  }, [toast]);
  if (!toast) return null;
  return createPortal(
    <p className="hearing-toast" role="status">
      {toast.message}
    </p>,
    document.body,
  );
}
