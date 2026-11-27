"use client";

import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { BACK_TO_TOP_MS, canHideHeaderFor, chromeAfterScroll, footerPlacement, fromBottom, hideForFooter, noScrollSlack, overlayFooterShown, overlayNeeded, remainingAt, showBackToTop } from "@/lib/hideOnScroll";
import type { ScrollSample } from "@/lib/hideOnScroll";

const IGNORED = 'input, textarea, select, [contenteditable="true"], [role="listbox"], [role="menu"], [role="dialog"], dialog, .recent-menu-popover, .app-drawer-menu';

const HEADER_FIELD = 'input, textarea, select, [contenteditable="true"], [role="combobox"]';
const HEADER_OPEN = 'details[open], [aria-expanded="true"]';

const BOTTOM_SLACK = 4;

function sample(el: HTMLElement): ScrollSample {
  return { top: el.scrollTop, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight };
}

function reducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function scrollToTop(el: HTMLElement) {
  if (reducedMotion()) {
    el.scrollTop = 0;
    return;
  }
  const startY = el.scrollTop;
  const startTime = performance.now();
  const step = (now: number) => {
    const progress = (now - startTime) / BACK_TO_TOP_MS;
    el.scrollTop = startY * remainingAt(progress);
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function firstScroller(page: HTMLElement, slack: number): HTMLElement | null {
  const all = [page, ...page.querySelectorAll<HTMLElement>("*")];
  for (const el of all) {
    if (el.scrollHeight - el.clientHeight <= slack) continue;
    const overflow = getComputedStyle(el).overflowY;
    if (overflow !== "auto" && overflow !== "scroll") continue;
    if (!el.getClientRects().length || el.closest(IGNORED)) continue;
    return el;
  }
  return null;
}

export function ScrollChrome({
  shellRef,
  pageRef,
  resetKey,
}: {
  shellRef: RefObject<HTMLElement | null>;
  pageRef: RefObject<HTMLElement | null>;

  resetKey: string;
}) {

  const [target, setTarget] = useState<{ el: HTMLElement; key: string } | null>(null);
  const keyRef = useRef(resetKey);
  const targetRef = useRef<HTMLElement | null>(null);
  const reset = useRef<() => void>(() => {});
  const showHeader = useRef<() => void>(() => {});

  useEffect(() => {
    const shell = shellRef.current;
    const page = pageRef.current;
    if (!shell || !page) return;
    const header = shell.querySelector<HTMLElement>(":scope > .app-header");
    const footer = shell.querySelector<HTMLElement>(":scope > .app-footer");
    const last = new WeakMap<Element, ScrollSample>();

    const runs = new WeakMap<Element, number>();
    let headerHidden = false;

    let owner: HTMLElement | null = null;

    let pinned = false;
    let reveal = -1;

    let flow = false;

    let distance: number | null = null;

    let overlay = false;
    let overlayShown = false;
    let spacerEl: HTMLElement | null = null;
    const headerBusy = () => {
      if (!header) return false;
      if (header.querySelector(HEADER_OPEN)) return true;
      const focused = document.activeElement;
      return focused instanceof HTMLElement && header.contains(focused) && focused.matches(HEADER_FIELD);
    };

    const setHeaderHidden = (next: boolean) => {
      if (next === headerHidden) return;
      headerHidden = next;
      if (next) shell.setAttribute("data-chrome", "hidden");
      else shell.removeAttribute("data-chrome");
      place(distance);
    };
    const setFlow = (next: boolean) => {
      if (next === flow) return;
      flow = next;
      if (next) shell.setAttribute("data-chrome-footer", "flow");
      else shell.removeAttribute("data-chrome-footer");
    };
    const setReveal = (px: number) => {
      const next = Math.round(px * 10) / 10;
      if (next === reveal) return;
      reveal = next;
      shell.style.setProperty("--chrome-footer-r", `${next}px`);
    };
    const footerHeight = () => footer?.offsetHeight ?? 0;
    const setOverlay = (next: boolean) => {
      const want = next ? owner : null;
      if (spacerEl && spacerEl !== want) spacerEl.removeAttribute("data-gap-room");
      spacerEl = want;
      spacerEl?.setAttribute("data-gap-room", "");
      if (next === overlay) return;
      overlay = next;
      if (next) shell.setAttribute("data-gap-footer", "");
      else shell.removeAttribute("data-gap-footer");
    };
    const setOverlayShown = (next: boolean) => {
      if (next === overlayShown) return;
      overlayShown = next;
      if (next) shell.setAttribute("data-gap-footer-shown", "");
      else shell.removeAttribute("data-gap-footer-shown");
    };
    const canHide = () => !!owner && canHideHeaderFor(sample(owner), header?.offsetHeight ?? 0, overlay ? footerHeight() : 0);

    const place = (nextDistance: number | null) => {
      distance = nextDistance;
      if (nextDistance === null && headerHidden) setHeaderHidden(false);
      const useOverlay = overlayNeeded({ distance: nextDistance, headerHidden, canHideHeader: canHide() });
      setOverlay(useOverlay);
      if (useOverlay) {

        setFlow(false);
        setReveal(0);
        setOverlayShown(overlayFooterShown({ distance: nextDistance, shown: overlayShown }));
        return;
      }
      setOverlayShown(false);
      const placed = footerPlacement({ distance: nextDistance, headerHidden, footerHeight: footerHeight() });
      setFlow(placed.flow);
      setReveal(placed.reveal);

      if (hideForFooter({ distance: nextDistance, headerHidden, canHideHeader: canHide() }) && !headerBusy()) setHeaderHidden(true);
    };

    const judge = () => {
      if (pinned) return;
      const slack = noScrollSlack(BOTTOM_SLACK, flow, footerHeight()) + (overlay ? footerHeight() : 0);
      if (!owner?.isConnected || owner.scrollHeight - owner.clientHeight <= slack) owner = firstScroller(page, slack);
      place(owner ? fromBottom(sample(owner)) : null);
    };
    let idleTimer: ReturnType<typeof setTimeout> | undefined;
    const judgeSoon = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(judge, 150);
    };

    showHeader.current = () => setHeaderHidden(false);
    reset.current = () => {
      setHeaderHidden(false);
      owner = null;
      pinned = false;
      judge();
      judgeSoon();
    };

    const measure = () => {
      shell.style.setProperty("--chrome-header-h", `${header?.offsetHeight ?? 0}px`);
      shell.style.setProperty("--chrome-footer-h", `${footerHeight()}px`);
    };
    measure();
    const resize = new ResizeObserver(() => {
      measure();
      judge();
      judgeSoon();
    });
    if (header) resize.observe(header);
    if (footer) resize.observe(footer);
    resize.observe(page);

    const mutations = new MutationObserver(judgeSoon);
    mutations.observe(page, { childList: true, subtree: true });
    judge();
    judgeSoon();

    const onScroll = (event: Event) => {
      const el = event.target;
      if (!(el instanceof HTMLElement) || el.closest(IGNORED)) return;
      const next = sample(el);
      const prev = last.get(el);
      last.set(el, next);
      if (!prev || prev.top !== next.top) {
        let run = 0;
        if (prev && prev.clientHeight === next.clientHeight) {
          const delta = next.top - prev.top;
          const before = runs.get(el) ?? 0;
          run = before !== 0 && Math.sign(before) === Math.sign(delta) ? before + delta : delta;
        }
        runs.set(el, run);
        const headerMove = chromeAfterScroll({
          prev,
          next,
          hidden: headerHidden,
          chromeHeight: header?.offsetHeight ?? 0,
          run,
        });
        if (headerMove === "show") setHeaderHidden(false);
        else if (headerMove === "hide" && !headerBusy()) setHeaderHidden(true);
        owner = el;
        pinned = false;
        place(fromBottom(next));
      }
      const wanted = showBackToTop(next) ? el : null;
      if (wanted !== targetRef.current && (wanted || targetRef.current === el)) {
        targetRef.current = wanted;
        setTarget(wanted ? { el: wanted, key: keyRef.current } : null);
      }
    };

    const onWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) setHeaderHidden(false);
    };

    const onFocusIn = (event: FocusEvent) => {
      if (!(event.target instanceof Node)) return;
      if (header?.contains(event.target)) setHeaderHidden(false);
      if (footer?.contains(event.target)) {

        pinned = true;
        setFlow(!headerHidden);
        setReveal(footerHeight());
      }
    };

    page.addEventListener("scroll", onScroll, { capture: true, passive: true });
    page.addEventListener("wheel", onWheel, { passive: true });
    shell.addEventListener("focusin", onFocusIn);
    return () => {
      page.removeEventListener("scroll", onScroll, { capture: true });
      page.removeEventListener("wheel", onWheel);
      shell.removeEventListener("focusin", onFocusIn);
      resize.disconnect();
      mutations.disconnect();
      clearTimeout(idleTimer);
      setHeaderHidden(false);
      shell.removeAttribute("data-chrome-footer");
      shell.removeAttribute("data-gap-footer");
      shell.removeAttribute("data-gap-footer-shown");
      spacerEl?.removeAttribute("data-gap-room");
      shell.style.removeProperty("--chrome-footer-r");
    };
  }, [shellRef, pageRef]);

  useEffect(() => {
    keyRef.current = resetKey;
    targetRef.current = null;
    reset.current();
  }, [resetKey]);

  const live = target !== null && target.key === resetKey && target.el.isConnected;

  function toTop() {
    const el = targetRef.current;
    showHeader.current();
    if (el) scrollToTop(el);

    shellRef.current?.querySelector<HTMLElement>(".app-header-brand")?.focus({ preventScroll: true });
  }

  return (
    <button
      type="button"
      className="back-to-top"
      title="Return to top"
      aria-label="Return to top"
      hidden={!live}
      onClick={toTop}
    >
      <i aria-hidden="true" />
    </button>
  );
}
