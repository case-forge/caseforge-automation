"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY = "caseforge-client-viewer:results-pane-width";
const MIN_WIDTH = 260;
const MAX_WIDTH = 640;
const DEFAULT_WIDTH = 352;

function clamp(width: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width));
}

function loadStoredWidth(): number {
  if (typeof window === "undefined") return DEFAULT_WIDTH;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? Number(raw) : NaN;
    return Number.isFinite(parsed) ? clamp(parsed) : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

export function useResultsPaneWidth(): [number, (next: number) => void] {
  const [width, setWidthState] = useState(DEFAULT_WIDTH);

  useEffect(() => {
    setWidthState(loadStoredWidth());
  }, []);

  const setWidth = useCallback((next: number) => {
    const clamped = clamp(next);
    setWidthState(clamped);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(clamped));
    } catch {

    }
  }, []);

  return [width, setWidth];
}

export function ResizeHandle({ width, onResize }: { width: number; onResize: (width: number) => void }) {
  const dragStart = useRef<{ startX: number; startWidth: number } | null>(null);

  useEffect(() => {
    function handlePointerMove(e: PointerEvent) {
      if (!dragStart.current) return;
      onResize(dragStart.current.startWidth + (e.clientX - dragStart.current.startX));
    }
    function handlePointerUp() {
      dragStart.current = null;
    }
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [onResize]);

  function handlePointerDown(e: React.PointerEvent) {
    dragStart.current = { startX: e.clientX, startWidth: width };
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowLeft") onResize(width - 16);
    else if (e.key === "ArrowRight") onResize(width + 16);
  }

  return (
    <div
      className="viewer-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the results and detail panels"
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={MAX_WIDTH}
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
    >
      <span className="viewer-resize-grip" aria-hidden="true">
        <span className="viewer-resize-arrow viewer-resize-arrow--left" />
        <span className="viewer-resize-line" />
        <span className="viewer-resize-arrow viewer-resize-arrow--right" />
      </span>
    </div>
  );
}
