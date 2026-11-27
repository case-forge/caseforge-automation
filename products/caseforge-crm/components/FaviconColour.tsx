"use client";

import { useEffect } from "react";
import { faviconColour, faviconHref, isMarkedTab, MARKED_COLOURS, recolourMark, svgDataHref, type FaviconColour as Colour } from "../lib/favicon";
import { faviconLock, subscribeFaviconLock } from "../lib/faviconLock";

function currentTheme(): "light" | "dark" {
  const set = document.documentElement.getAttribute("data-theme");
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

let blackMark: string | null = null;
let blackMarkAsked = false;

export function applyFavicon(): Colour {
  document.querySelectorAll('link[rel~="icon"]').forEach((el) => {
    if (el.id !== "app-favicon") el.remove();
  });
  let link = document.getElementById("app-favicon") as HTMLLinkElement | null;
  const colour = faviconLock() ?? faviconColour(currentTheme());
  if (!link) {
    link = document.createElement("link");
    link.id = "app-favicon";
    link.rel = "icon";
    document.head.appendChild(link);
  }
  const marked = isMarkedTab(window.location.hostname, process.env.NEXT_PUBLIC_CASEFORGE_DEMO === "1");

  const href = marked && blackMark ? svgDataHref(recolourMark(blackMark, MARKED_COLOURS[currentTheme()])) : faviconHref(colour);
  if (link.getAttribute("href") !== href) {
    link.setAttribute("type", "image/svg+xml");
    link.setAttribute("href", href);
  }
  if (marked && blackMark === null && !blackMarkAsked) {
    blackMarkAsked = true;
    fetch(faviconHref("black"))
      .then((res) => (res.ok ? res.text() : ""))
      .then((svg) => {
        if (svg.includes("<svg")) {
          blackMark = svg;
          applyFavicon();
        }
      })
      .catch(() => undefined);
  }
  return colour;
}

export function FaviconColour() {
  useEffect(() => {
    const apply = () => applyFavicon();
    apply();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const headObserver = new MutationObserver(apply);
    headObserver.observe(document.head, { childList: true });
    media.addEventListener("change", apply);
    const unsubscribe = subscribeFaviconLock(apply);
    return () => {
      unsubscribe();
      observer.disconnect();
      headObserver.disconnect();
      media.removeEventListener("change", apply);
    };
  }, []);
  return null;
}
