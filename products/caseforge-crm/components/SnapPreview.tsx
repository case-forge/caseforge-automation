"use client";

import { useSnapPreview } from "@/lib/windowSnap";
import { slotCentres, slotTargets, tabHeight } from "@/lib/demoDock";
import { SLOT_HALF_PX, gapZones } from "@/lib/windowGesture";
import { headerBottom, viewportWidth } from "@/lib/demoWindows";
import { useDockCue } from "@/lib/dockGesture";

export function SnapPreview() {
  const box = useSnapPreview();
  if (!box) return null;
  return <div className="fw-snap-preview" aria-hidden="true" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />;
}

export function DockGhost() {
  const cue = useDockCue();
  if (!cue) return null;
  const vp = { w: viewportWidth(), h: window.innerHeight, top: headerBottom() };
  const h = tabHeight(cue.title);
  const top = slotCentres(vp)[cue.slot] - h / 2;
  return (
    <>
      <div className={`fw-tab-targets fw-dock-targets${cue.on ? " fw-dock-targets-on" : ""}`} aria-hidden="true">
        {slotTargets(vp).map((t) => (
          <span key={`${t.side}-${t.slot}`} className={`fw-tab-target fw-tab-target-${t.side}${cue.on && cue.over === "slot" && t.side === cue.side && t.slot === cue.slot ? " fw-tab-target-on" : ""}`} style={{ top: t.y - SLOT_HALF_PX }} />
        ))}
        {cue.gaps &&
          (["left", "right"] as const).flatMap((side) =>
            gapZones(vp).map((g, i) => (
              <span key={`gap-${side}-${i}`} className={`fw-gap-zone fw-gap-zone-${side}${cue.on && cue.over === "gap" && side === cue.side && i === cue.gap ? " fw-gap-zone-on" : ""}`} style={{ top: g.y, height: g.h }} />
            )),
          )}
      </div>
      <div className={`fw-dock-ghost fw-dock-ghost-${cue.side}${cue.on && cue.over === "slot" ? " fw-dock-ghost-on" : ""}`} aria-hidden="true" style={{ top, height: h }}>
        <span className="fw-tab-title">{cue.title}</span>
      </div>
    </>
  );
}
