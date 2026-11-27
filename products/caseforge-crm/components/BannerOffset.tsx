"use client";

import { useEffect } from "react";
import { BANNER_SELECTOR } from "@/lib/demoWindows";

export function BannerOffset() {
  useEffect(() => {
    const root = document.documentElement;
    let frame = 0;
    const resizes = new ResizeObserver(() => schedule());
    const watched = new Set<Element>();

    function measure() {
      frame = 0;
      const banners = Array.from(document.querySelectorAll(BANNER_SELECTOR));
      for (const el of banners) {
        if (!watched.has(el)) {
          watched.add(el);
          resizes.observe(el);
        }
      }
      for (const el of Array.from(watched)) {
        if (!banners.includes(el)) {
          watched.delete(el);
          resizes.unobserve(el);
        }
      }
      const height = banners.reduce((sum, el) => sum + (el as HTMLElement).offsetHeight, 0);
      root.style.setProperty("--banner-h", `${height}px`);
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(measure);
    }

    const changes = new MutationObserver(schedule);
    changes.observe(document.body, { childList: true, subtree: true });
    measure();
    return () => {
      if (frame) cancelAnimationFrame(frame);
      changes.disconnect();
      resizes.disconnect();
      root.style.removeProperty("--banner-h");
    };
  }, []);

  return null;
}
