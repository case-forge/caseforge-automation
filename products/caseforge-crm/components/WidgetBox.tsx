"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { CardBar } from "@/components/CardBar";
import { consumeRequest, useOpenRequests, useReportShowing } from "@/lib/cornerPrompts";
import type { CornerId } from "@/lib/cornerPrompts";
import { minimisedTabs } from "@/lib/minimisedTabs";
import { usePresentNode } from "@/lib/presence";
import { usePersistedOpen } from "@/lib/widgetOpen";
import { useFloatingBox } from "@/lib/useFloatingBox";
import { RESIZE_EDGES } from "@/lib/demoWindows";
import { windowPins } from "@/lib/windowPins";

export function WidgetBox({
  corner,
  boxId,
  title,
  className,
  extras,
  onOpened,
  children,
}: {
  corner: CornerId;

  boxId: string;
  title: string;
  className: string;
  extras?: ReactNode;

  onOpened?: () => void;
  children: ReactNode;
}) {
  const [open, setOpen] = usePersistedOpen(boxId);
  const win = useFloatingBox(boxId, title);
  const asked = useOpenRequests(corner);

  useEffect(() => {
    if (!consumeRequest(corner)) return;
    setOpen(true);
    minimisedTabs.remove(boxId);
    onOpened?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked]);

  const hide = () => {
    if (win.pinned) windowPins.toggle(boxId);
    win.restore();
    setOpen(false);
  };
  useReportShowing(corner, open && !win.minimised, hide);

  const present = usePresentNode(open, (phase, onAnimationEnd) => (
    <aside
      ref={win.windowRef as React.RefObject<HTMLElement>}
      className={`${className} widget-box fw fw-card ${win.windowClass} widget-${phase}`}
      {...win.windowAttrs}
      role="dialog"
      aria-label={title}
      aria-hidden={win.minimised || phase === "closing" || undefined}
      style={win.style}
      onAnimationEnd={onAnimationEnd}
      onKeyDown={(e) => {

        if (e.key === "Escape" && !e.defaultPrevented) hide();
      }}
    >
      <CardBar id={boxId} title={title} pinned={win.pinned} onClose={hide} closeHint="Hide (keeps what is in it)" onMinimise={win.minimise} barProps={win.barProps} extras={extras} />
      <div className="fw-body">{children}</div>
      {!win.maximised && !win.pinned && RESIZE_EDGES.map((edge) => <div key={edge} className={`fw-grip fw-grip-${edge}`} aria-hidden="true" {...win.gripProps(edge)} />)}
    </aside>
  ));

  return present;
}
