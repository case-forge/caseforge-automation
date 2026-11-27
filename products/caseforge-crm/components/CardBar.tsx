"use client";

import { useLayoutEffect, useRef } from "react";
import { minWidthFor } from "@/lib/titleWidth";
import type { HTMLAttributes, ReactNode } from "react";
import { WindowActions } from "./WindowActions";

export function CardBar({
  id,
  title,
  windowName = "window",
  onClose,
  closeHint = "Close",
  onMinimise,
  pinned = false,
  extras,
  barProps,
  dragLabel = "Drag to move; arrow keys move it, Escape puts it back",
}: {

  id: string;
  title: ReactNode;

  windowName?: string;
  onClose: () => void;
  closeHint?: string;
  onMinimise: () => void;
  pinned?: boolean;

  extras?: ReactNode;
  barProps: HTMLAttributes<HTMLElement>;
  dragLabel?: string;
}) {
  const barRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLSpanElement>(null);
  const label = typeof title === "string" ? title : windowName;

  useLayoutEffect(() => {
    const bar = barRef.current;
    const win = bar?.closest<HTMLElement>(".fw");
    const titleEl = titleRef.current;
    if (!bar || !win || !titleEl) return;
    const sample = (titleEl.firstElementChild as HTMLElement | null) ?? titleEl;
    const style = getComputedStyle(sample);
    const barStyle = getComputedStyle(bar);

    const others = [...bar.children]
      .filter((k) => k !== titleEl)
      .map((k) => {
        const m = getComputedStyle(k);
        return (k as HTMLElement).offsetWidth + (parseFloat(m.marginLeft) || 0) + (parseFloat(m.marginRight) || 0);
      });
    const need = minWidthFor({
      titleText: titleEl.textContent ?? "",
      font: `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`,
      otherWidths: others,
      gap: parseFloat(barStyle.columnGap) || 0,
      padding: (parseFloat(barStyle.paddingLeft) || 0) + (parseFloat(barStyle.paddingRight) || 0),

      border: 8,
    });
    win.style.setProperty("--fw-min-w", `${need}px`);
  });

  return (
    <div className="fw-bar fw-bar--card" ref={barRef} tabIndex={barProps.onKeyDown ? 0 : undefined} title={barProps.onKeyDown ? dragLabel : undefined} {...barProps}>
      <span className="fw-title fw-title--card" ref={titleRef}>
        {title}
      </span>
      {extras && <span className="fw-extras">{extras}</span>}
      <WindowActions id={id} title={label} pinned={pinned} onMinimise={onMinimise} onClose={onClose} closeHint={closeHint} />
    </div>
  );
}
