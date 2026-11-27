"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CardBar } from "@/components/CardBar";
import { IconExternalLink, IconHelp } from "@/components/icons";
import { consumeRequest, markClosed, useOpenRequests, useReportShowing } from "@/lib/cornerPrompts";
import { usePresentNode } from "@/lib/presence";
import { minimisedTabs } from "@/lib/minimisedTabs";
import { classifierPromptsOn, useClassifierPrompts } from "@/lib/classifierPrompts";
import { useFloatingBox } from "@/lib/useFloatingBox";
import { RESIZE_EDGES } from "@/lib/demoWindows";
import {
  isTypingTarget,
  isUndecided,
  loadPromptMemory,
  holdAfterClose,
  holdAfterNotToday,
  poolBadge,
  safeEmailLink,
  promptAllowed,
  promptQuestion,
  savePromptMemory,
  type ControlView,
} from "@/lib/mailReview";

const FIRST_LOOK_MS = 45_000;
const RECHECK_MS = 60_000;

const CHANGE_WINDOW_MS = 30_000;

function releaseItem(jobId: string): void {
  void fetch("/api/mail-review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "control_release", job_id: jobId }),
  }).catch(() => undefined);
}

export function ClassifierPrompt() {
  const [enabled, setEnabled] = useClassifierPrompts();
  const [view, setView] = useState<ControlView | null>(null);
  const [mode, setMode] = useState<"agree" | "disagree" | null>(null);
  const [comment, setComment] = useState("");
  const [route, setRoute] = useState("");
  const [otherText, setOtherText] = useState("");
  const [busy, setBusy] = useState(false);
  const [thanks, setThanks] = useState(false);
  const [why, setWhy] = useState(false);
  const [lastAnswered, setLastAnswered] = useState<ControlView | null>(null);
  const thanksTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const asked = useOpenRequests("classifier");
  const [empty, setEmpty] = useState(false);
  const shown = useRef(false);
  const win = useFloatingBox("classifier-prompt", "Email classifier");

  useEffect(() => {
    if (!enabled) return;
    if (window.location.pathname.startsWith("/review-mail") || window.location.pathname.startsWith("/settings")) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function look() {
      if (cancelled || shown.current || !classifierPromptsOn()) return;
      const now = Date.now();
      const memory = loadPromptMemory();
      const typing = isTypingTarget(document.activeElement);
      if (document.hidden || !promptAllowed(memory, now, typing)) {
        timer = setTimeout(() => void look(), RECHECK_MS);
        return;
      }
      try {
        const res = await fetch("/api/mail-review?view=batch", { cache: "no-store" });
        const body = (await res.json().catch(() => null)) as ControlView | null;
        if (cancelled) return;

        if (!res.ok || !body || !body.item) {
          savePromptMemory({ ...memory, lastShownAt: now });
          return;
        }
        if (isTypingTarget(document.activeElement)) {
          releaseItem(body.item.job_id);
          timer = setTimeout(() => void look(), RECHECK_MS);
          return;
        }
        shown.current = true;
        savePromptMemory({ ...memory, lastShownAt: Date.now() });
        setView(body);
      } catch {
        savePromptMemory({ ...memory, lastShownAt: now });
      }
    }

    timer = setTimeout(() => void look(), FIRST_LOOK_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [enabled]);

  useEffect(() => {
    if (!consumeRequest("classifier")) return;
    let cancelled = false;
    minimisedTabs.remove("classifier-prompt");
    void fetch("/api/mail-review?view=batch", { cache: "no-store" })
      .then((res) => res.json().catch(() => null) as Promise<ControlView | null>)
      .then((body) => {
        if (cancelled) return;
        if (body?.item) {
          shown.current = true;
          setEmpty(false);
          setView(body);
        } else {
          setEmpty(true);
        }
      })
      .catch(() => !cancelled && setEmpty(true));
    return () => {
      cancelled = true;
    };
  }, [asked]);

  function changeAnswer() {
    if (!lastAnswered) return;
    if (thanksTimer.current) clearTimeout(thanksTimer.current);
    setThanks(false);
    setMode(null);
    setComment("");
    setRoute("");
    setView(lastAnswered);
    setLastAnswered(null);
  }

  function hold(until: "hour" | "tomorrow") {
    const jobId = view?.item?.job_id;
    savePromptMemory(until === "hour" ? holdAfterClose(Date.now()) : holdAfterNotToday(Date.now()));
    if (jobId) releaseItem(jobId);
    setView(null);
    shown.current = true;
  }
  const dismiss = () => hold("hour");
  const notToday = () => hold("tomorrow");

  function toggleEnabled() {
    if (enabled) {
      setEnabled(false);
      dismiss();
    } else {
      setEnabled(true);
    }
  }

  async function answer(verdict: "agree" | "disagree") {
    const item = view?.item;
    if (!item || !view || busy) return;
    const chosen = verdict === "disagree" || isUndecided(item.applied_route) ? route : "";
    if (verdict === "disagree" && !chosen) return;
    if (chosen === "Other" && !otherText.trim()) return;
    setBusy(true);
    try {
      const res = await fetch("/api/mail-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "control", date: view.date, job_id: item.job_id, verdict, route: chosen, other_text: chosen === "Other" ? otherText.trim() : "", logic: comment.trim() }),
      });
      if (res.ok) {

        savePromptMemory({ ...loadPromptMemory(), lastShownAt: Date.now() });
        setThanks(true);
        setMode(null);
        setComment("");
        setRoute("");
        setOtherText("");
        setLastAnswered(view);
        setView(null);
        if (thanksTimer.current) clearTimeout(thanksTimer.current);
        thanksTimer.current = setTimeout(() => {
          setThanks(false);
          setLastAnswered(null);
        }, CHANGE_WINDOW_MS);
      }
    } catch {

    } finally {
      setBusy(false);
    }
  }

  const item = view?.item ?? null;
  const closeCard = () => { win.restore(); markClosed("classifier"); setEmpty(false); if (item) dismiss(); else { setThanks(false); setLastAnswered(null); } };
  useReportShowing("classifier", !!(item || thanks || empty) && !win.minimised, closeCard);
  const shownNow = !!(item || thanks || empty);
  const undecided = item ? isUndecided(item.applied_route) : false;
  const picking = mode === "disagree" || undecided;
  const answering = mode !== null || undecided;
  const question = item ? promptQuestion(item) : null;
  const badge = item ? poolBadge(item.pool) : null;
  const emailLink = item ? safeEmailLink(item.weblink) : "";

  return usePresentNode(shownNow, (phase, onAnimationEnd) => (
    <aside ref={win.windowRef as React.RefObject<HTMLElement>} style={win.style} className={`classifier-prompt fw fw-card ${win.windowClass} widget-${phase}`} {...win.windowAttrs} aria-hidden={win.minimised || phase === "closing" || undefined} aria-label="Help improve email classifier" onAnimationEnd={onAnimationEnd} onKeyDown={(e) => { if (e.key === "Escape" && item) dismiss(); }}>
      <CardBar
        id="classifier-prompt"
        pinned={win.pinned}
        title="Help improve email classifier"
        onClose={closeCard}
        closeHint={item ? "Close (asks again in an hour)" : "Close"}
        onMinimise={win.minimise}
        barProps={win.barProps}
        extras={
          item && (
            <>
              {badge && (
                <span className={`classifier-badge classifier-badge--${badge.letter.toLowerCase()}`} tabIndex={0} role="img" aria-label={badge.tip} title={badge.tip}>
                  {badge.letter}
                </span>
              )}
              <button type="button" className="cf-btn cf-btn--icon" aria-label="Why am I being asked?" title="Why am I being asked?" aria-expanded={why} aria-controls="classifier-prompt-why" onClick={() => setWhy(!why)}>
                <IconHelp aria-hidden="true" />
              </button>
            </>
          )
        }
      />
      <div className="fw-body">
      {empty && !item && (
        <p role="status" className="classifier-prompt-thanks">
          No email needs checking just now.
        </p>
      )}
      {thanks && (
        <p role="status" className="classifier-prompt-thanks">
          Thank you. Your answer helps the sorter get better.{" "}
          {lastAnswered && <button type="button" className="cf-btn cf-btn--link" onClick={changeAnswer}>Change my answer</button>}
        </p>
      )}
      {item && view && question && (
        <>
          {why && (
            <p id="classifier-prompt-why" className="classifier-prompt-hint">
              Our sorter files incoming email by itself. Your answer checks its work and teaches it to get better. Nobody else is shown this email at the same time, and you are asked at most once an hour.
            </p>
          )}
          <p className="classifier-prompt-mail">
            <span className="classifier-prompt-label">From</span> {item.from}
            <br />
            <span className="classifier-prompt-label">To</span> {item.to}
            {item.cc && (
              <>
                <br />
                <span className="classifier-prompt-label">Cc</span> {item.cc}
              </>
            )}
            <br />
            <span className="classifier-prompt-label">Subject</span> {item.subject}
            {emailLink && (
              <>
                <br />
                <a className="classifier-prompt-email-link" href={emailLink} target="_blank" rel="noopener noreferrer">
                  <IconExternalLink aria-hidden="true" /> Open the email<span className="review-mail-sr"> (opens in a new tab)</span>
                </a>
              </>
            )}
          </p>
          <p>
            {question.lead} <strong>{question.ask}</strong>
          </p>
          {answering ? (
            <>
              {picking && (
                <div className="classifier-prompt-pick">
                  <label>
                    Where it belongs
                    <select value={route} onChange={(e) => setRoute(e.target.value)}>
                      <option value="">Choose</option>
                      {view.routes.filter((r) => r !== (item.applied_destination || item.applied_route)).map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </label>
                  {route === "Other" && (
                    <label>
                      Where does it go?
                      <input type="text" value={otherText} maxLength={80} onChange={(e) => setOtherText(e.target.value)} placeholder="Type the folder or person" />
                    </label>
                  )}
                </div>
              )}
              <label className="classifier-prompt-comment">
                Comment (optional)
                <textarea
                  rows={2}
                  maxLength={2000}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder={mode === "agree" ? "Anything worth adding?" : "What should it have noticed?"}
                />
              </label>
              <div className="classifier-prompt-actions">
                {!undecided && (
                  <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy} onClick={() => { setMode(null); setRoute(""); setOtherText(""); setComment(""); }}>Back</button>
                )}
                <button
                  type="button"
                  className="cf-btn cf-btn--primary cf-btn--small"
                  disabled={busy || (picking && (!route || (route === "Other" && !otherText.trim())))}
                  onClick={() => void answer(picking ? "disagree" : "agree")}
                >
                  Save
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="classifier-prompt-actions">
                <button type="button" className="cf-btn cf-btn--primary cf-btn--small" disabled={busy} onClick={() => setMode("agree")}>Agree</button>
                <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" disabled={busy} onClick={() => setMode("disagree")}>Disagree</button>
              </div>
              <p className="classifier-prompt-hint">Agree confirms it. Disagree lets you pick the right place. Either way you can add a comment.</p>
            </>
          )}
          <div className="classifier-prompt-foot">
            <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" title="Ask again tomorrow" onClick={notToday}>Not today</button>
            <Link className="cf-btn cf-btn--neutral cf-btn--small" href="/review-mail?tab=control" target="_blank" rel="noopener noreferrer" aria-label="Check more mail (opens in a new tab)" title="Check more mail (opens in a new tab)">
              Check more mail <IconExternalLink aria-hidden="true" />
            </Link>
            <button type="button" className="cf-btn cf-btn--neutral cf-btn--small" aria-pressed={!enabled} title={enabled ? "Stop these questions appearing on their own" : "Let these questions appear again"} onClick={toggleEnabled}>
              {enabled ? "Turn these off" : "Turn these on"}
            </button>
          </div>
        </>
      )}
      </div>
      {!win.maximised && !win.pinned && RESIZE_EDGES.map((edge) => <div key={edge} className={`fw-grip fw-grip-${edge}`} aria-hidden="true" {...win.gripProps(edge)} />)}
    </aside>
  ));
}
