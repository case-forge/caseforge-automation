"use client";

import { useEffect, useRef, useState } from "react";
import { IconRefresh } from "./icons";
import { onSessionStale } from "@/lib/sessionStale";
import { reportSessionExpiry, useSessionCountdown } from "@/lib/sessionExpiry";
import {
  PROBE_INIT,
  RECONNECTING_TEXT,
  RECONNECT_START,
  STILL_UNREACHABLE_TEXT,
  classifyResponse,
  reconnectReducer,
  retryDelayMs,
} from "@/lib/sessionProbe";
import type { ReconnectNote, ReconnectState } from "@/lib/sessionProbe";
import { startVisiblePoll } from "@/lib/visiblePoll";
import { backgroundFetch } from "@/lib/loadingBar";
import { describeUnsaved, reloadKeepingDrafts, unsavedSources } from "@/lib/unsavedEdits";
import type { UnsavedSource } from "@/lib/unsavedEdits";

const POLL_MS = 30_000;
const WARN_BEFORE_MS = 5 * 60_000;

type BannerState = "none" | "new-version" | "session-expiring-soon" | "session-stale";

function formatClock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function sessionExpiringMessage(expiresAt: number | null): string {
  return `Your session will expire soon${expiresAt ? `, around ${formatClock(expiresAt)}` : ""}`;
}

function UnsavedRefreshNotice({
  onShow,
  onClose,
}: {
  onShow: (source: UnsavedSource) => void;
  onClose: () => void;
}) {
  const [open, setOpen] = useState<UnsavedSource[]>(() => unsavedSources());

  useEffect(() => {
    const timer = window.setInterval(() => setOpen(unsavedSources()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="refresh-unsaved" role="alert">
      <p className="refresh-unsaved-lead">
        {open.length > 0
          ? "Your unsaved edits are kept as drafts and come back when you open them again."
          : "Nothing is unsaved now."}
      </p>
      {open.length > 0 && (
        <ul className="refresh-unsaved-list">
          {open.map((source) => (
            <li key={source.id}>
              <span>Unsaved: {describeUnsaved(source)}</span>
              <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={() => onShow(source)}>
                Show me
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="refresh-unsaved-actions">
        <button type="button" className="cf-btn cf-btn--primary cf-btn--small refresh-unsaved-go" onClick={reloadKeepingDrafts} autoFocus>
          Refresh now
        </button>
        <button type="button" className="cf-btn cf-btn--flush cf-btn--small" onClick={onClose}>
          Not yet
        </button>
      </div>
    </div>
  );
}

export function UpdateBanner({ onShowUnsaved }: { onShowUnsaved: (source: UnsavedSource) => void }) {
  const [state, setState] = useState<BannerState>("none");
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [expiresAt, setExpiresAt] = useState<number | null>(null);
  const [note, setNote] = useState<ReconnectNote>("none");

  const countdown = useSessionCountdown();
  const reconnect = useRef<ReconnectState>(RECONNECT_START);
  const initialBuildId = useRef<string | null>(null);

  const staleRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    function goStale() {
      if (cancelled) return;
      staleRef.current = true;
      setState("session-stale");
    }

    let retryTimer: number | undefined;

    function record(event: Parameters<typeof reconnectReducer>[1]) {
      reconnect.current = reconnectReducer(reconnect.current, event);
      if (!cancelled) setNote(reconnect.current.note);
    }

    function failed() {
      if (cancelled) return;
      record({ type: "failure", now: Date.now() });
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => void check(), retryDelayMs(reconnect.current.failures));
    }

    async function check() {
      if (staleRef.current || cancelled) return;
      try {
        const res = await backgroundFetch("/api/version", { cache: "no-store", ...PROBE_INIT });
        const probe = await classifyResponse(res);
        if (probe === "access-expired") {
          goStale();
          return;
        }
        if (probe === "unreachable") {
          failed();
          return;
        }
        window.clearTimeout(retryTimer);
        record({ type: "success" });
        const body = (await res.json()) as { buildId?: string; sessionExpiresAt?: number | null };

        const buildId = body.buildId ?? "";
        if (buildId) {
          if (initialBuildId.current === null) {
            initialBuildId.current = buildId;
          } else if (!cancelled && buildId !== initialBuildId.current) {
            setState((current) => (current === "none" ? "new-version" : current));
          }
        }

        if (typeof body.sessionExpiresAt === "number") {
          setExpiresAt(body.sessionExpiresAt);
          reportSessionExpiry(body.sessionExpiresAt);
          const remaining = body.sessionExpiresAt - Date.now();
          if (remaining <= 0) {
            goStale();
          } else if (remaining <= WARN_BEFORE_MS && !cancelled) {
            setState((current) => (current === "none" || current === "session-expiring-soon" ? "session-expiring-soon" : current));
          }
        }
      } catch {

        failed();
      }
    }

    const stopPoll = startVisiblePoll(() => void check(), POLL_MS);
    const unsubscribe = onSessionStale(goStale);
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
      stopPoll();
      unsubscribe();
    };
  }, []);

  if (state === "none") {
    if (note === "none") return null;
    return (
      <div className="update-banner" role="status" aria-live="polite">
        <span>{note === "still-unreachable" ? STILL_UNREACHABLE_TEXT : RECONNECTING_TEXT}</span>
      </div>
    );
  }

  function handleRefresh() {

    if (unsavedSources().length === 0) {
      reloadKeepingDrafts();
      return;
    }
    setNoticeOpen(true);
  }

  const notice = noticeOpen && <UnsavedRefreshNotice onShow={onShowUnsaved} onClose={() => setNoticeOpen(false)} />;

  if (state === "session-stale") {
    return (
      <div className="session-stale-wrap">
      <div className="session-stale-banner" role="alert">
        <span>
          <strong>Your session has expired.</strong> Reload the page to log in again.
        </span>
        <button type="button" className="cf-btn cf-btn--primary cf-btn--danger cf-btn--small session-stale-button" onClick={handleRefresh} autoFocus>
          <IconRefresh aria-hidden="true" />
          Refresh now
        </button>
      </div>
      {notice}
      </div>
    );
  }

  if (state === "session-expiring-soon") {
    return (
      <div className="update-banner" role="status">
        <span>{sessionExpiringMessage(expiresAt)}</span>
        {countdown && <span className="update-banner-timer" role="timer">{countdown} left</span>}
      </div>
    );
  }

  return (
    <>
      <div className="update-banner" role="status">
        <span>A new version is available.</span>
        <button type="button" className="cf-btn cf-btn--primary cf-btn--small" onClick={handleRefresh}>
          Refresh page
        </button>
      </div>
      {notice}
    </>
  );
}
