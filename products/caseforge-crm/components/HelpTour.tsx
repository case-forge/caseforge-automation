"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useModalFocus } from "@/lib/modalFocus";
import { createPortal } from "react-dom";
import { availableHelpSteps, findHelpTarget, HEADER_HELP_STEPS, HELP_STEPS } from "@/lib/helpTour";
import type { HelpStep } from "@/lib/helpTour";
import { IconHelp } from "./icons";
import { IS_DEMO } from "./HeaderClock";

function setMenu(open: boolean) {
  const drawer = document.querySelector<HTMLDetailsElement>("details.app-drawer");
  if (drawer && drawer.open !== open) drawer.open = open;
}

export function HelpMenuEntry() {
  const list: HelpStep[] = IS_DEMO ? HELP_STEPS : HEADER_HELP_STEPS;
  const [steps, setSteps] = useState<number[] | null>(null);
  const [at, setAt] = useState(0);
  const dim = useRef<HTMLDivElement>(null);
  const menuByTour = useRef(false);

  const step = steps ? list[steps[at]] : null;
  const cardRef = useModalFocus<HTMLDivElement>(Boolean(step));

  const close = useCallback(() => {
    if (menuByTour.current) setMenu(false);
    menuByTour.current = false;
    setSteps(null);
  }, []);

  const go = useCallback(
    (next: number) => {
      if (!steps) return;
      const clamped = Math.min(Math.max(next, 0), steps.length - 1);
      const target = list[steps[clamped]];
      if (target.openMenu) {
        setMenu(true);
        menuByTour.current = true;
      } else if (menuByTour.current) {
        setMenu(false);
        menuByTour.current = false;
      }
      setAt(clamped);
    },
    [steps, list],
  );

  function start() {

    window.requestAnimationFrame(() => {
      setSteps(availableHelpSteps(document, true, list));
      setAt(0);
    });
  }

  useEffect(() => {
    if (!step) return;
    let raf = 0;
    const tick = () => {
      const el = dim.current;
      if (el) {
        const target = findHelpTarget(step);
        if (!target) {
          el.style.clipPath = "";
        } else {
          const r = target.getBoundingClientRect();
          const pad = 8;
          const t = Math.max(0, r.top - pad);
          const l = Math.max(0, r.left - pad);
          const b = Math.min(window.innerHeight, r.bottom + pad);
          const rt = Math.min(window.innerWidth, r.right + pad);
          const w = window.innerWidth;
          const h = window.innerHeight;
          const clip = `polygon(0px 0px,0px ${h}px,${l}px ${h}px,${l}px ${t}px,${rt}px ${t}px,${rt}px ${b}px,${l}px ${b}px,${l}px ${h}px,${w}px ${h}px,${w}px 0px)`;
          if (el.style.clipPath !== clip) el.style.clipPath = clip;
        }
      }
      raf = window.requestAnimationFrame(tick);
    };
    raf = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(raf);
  }, [step]);

  useEffect(() => {
    if (!steps) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if (event.key === "ArrowRight" && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        go(at + 1);
      } else if (event.key === "ArrowLeft" && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        go(at - 1);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [steps, at, go, close]);

  useEffect(() => {
    if (step?.openMenu) setMenu(true);
  }, [step]);

  const last = steps ? at >= steps.length - 1 : true;

  return (
    <>
      <button type="button" className="cf-btn cf-btn--flush app-drawer-quick-list-item" data-menu-close="" onClick={start}>
        <IconHelp aria-hidden="true" />
        <span>Help</span>
      </button>
      { }
      {steps && step && createPortal(
        <>
          <div className="help-tour-dim" ref={dim} aria-hidden="true" />
          <div className="help-tour-card" ref={cardRef} role="dialog" aria-modal="true" aria-label={step.title}>
            <div className="help-tour-head">
              <div>
                <div className="help-tour-count">{at + 1} of {steps.length}</div>
                <h2 className="help-tour-title">{step.title}</h2>
              </div>
              <button type="button" className="cf-btn cf-btn--flush cf-btn--small help-tour-skip" onClick={close}>Skip tour</button>
            </div>
            <p className="help-tour-text">{step.text}</p>
            <div className="help-tour-foot">
              <span className="help-tour-dots" aria-hidden="true">
                {steps.map((_, i) => (
                  <span key={i} className={`help-tour-dot${i === at ? " help-tour-dot-on" : ""}`} />
                ))}
              </span>
              <span className="help-tour-buttons">
                {at > 0 && <button type="button" className="cf-btn cf-btn--neutral help-tour-back" onClick={() => go(at - 1)}>Back</button>}
                <button type="button" className="cf-btn cf-btn--primary help-tour-next" onClick={() => (last ? close() : go(at + 1))} autoFocus>
                  {last ? "Finish" : "Next"}
                </button>
              </span>
            </div>
          </div>
        </>,
        document.body,
      )}
    </>
  );
}
