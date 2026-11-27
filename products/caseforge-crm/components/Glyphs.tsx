
import type { ReactNode } from "react";
import { IconAlert, IconBan, IconCheck, IconCircle, IconCircleCheck, IconCircleDashed, IconClose, IconDna, IconHelp, IconPencil } from "./icons";

export const SYNC_BARS = 4;

export function SyncGlyph({ level }: { level: number | null }) {
  if (level === null) return null;
  const on = Math.max(0, Math.min(SYNC_BARS, level));
  return (
    <span className="sync-glyph" aria-hidden="true" data-level={on}>
      <IconDna />
      <span className="sync-bars">
        {Array.from({ length: SYNC_BARS }, (_, i) => (
          <span key={i} className="sync-bar" data-on={i < on ? "true" : undefined} />
        ))}
      </span>
    </span>
  );
}

const SHAPE_ICON: Record<string, () => ReactNode> = {
  "●": () => <IconCircleCheck />,
  "○": () => <IconCircle />,
  "▲": () => <IconAlert />,
  "■": () => <IconBan />,
  "◇": () => <IconHelp />,
  "◌": () => <IconCircleDashed />,
};

export function StatusShape({ shape }: { shape: string }) {
  const draw = SHAPE_ICON[shape];
  return (
    <span className="status-shape" aria-hidden="true">
      {draw ? draw() : shape}
    </span>
  );
}

const LEAD_ICON: Record<string, () => ReactNode> = {
  "✓": () => <IconCheck />,
  "✕": () => <IconClose />,
  "✎": () => <IconPencil />,
};

export function LeadGlyphText({ label }: { label: string }) {
  const draw = LEAD_ICON[label.charAt(0)];
  if (!draw || label.charAt(1) !== " ") return <>{label}</>;
  return (
    <>
      <span className="status-shape" aria-hidden="true">
        {draw()}
      </span>{" "}
      {label.slice(2)}
    </>
  );
}
