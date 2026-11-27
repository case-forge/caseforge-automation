"use client";

import { useEffect, useSyncExternalStore } from "react";
import { countFetches, loadingBar } from "@/lib/loadingBar";

export function LoadingBar() {
  const state = useSyncExternalStore(loadingBar.subscribe, loadingBar.getState, loadingBar.getState);

  const stuck = state.visible && state.progress >= 60 ? state.waiting.join(", ") : "";
  useEffect(() => {
    if (stuck) console.warn(`[loading bar] still waiting on: ${stuck}`);
  }, [stuck]);

  useEffect(() => {
    const original = window.fetch;
    window.fetch = countFetches(original);
    let loadHeld = false;
    if (document.readyState !== "complete") {
      loadHeld = true;
      loadingBar.begin();
    }
    const onLoad = () => {
      if (loadHeld) {
        loadHeld = false;
        loadingBar.end();
      }
    };
    window.addEventListener("load", onLoad);
    return () => {
      window.removeEventListener("load", onLoad);
      window.fetch = original;
      onLoad();
    };
  }, []);

  return (
    <div className="loading-bar" role="progressbar" aria-label="Loading" aria-hidden={!state.visible} data-visible={state.visible ? "true" : "false"} data-waiting={state.waiting.join(" ")}>
      <div className="loading-bar-fill" style={{ transform: `scaleX(${state.progress / 100})` }} />
    </div>
  );
}
