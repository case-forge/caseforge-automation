"use client";

import { windowPins } from "@/lib/windowPins";
import { IconClose, IconMinus, IconPin } from "./icons";

export function WindowActions({
  id,
  title,
  pinned,
  onMinimise,
  onClose,
  closeHint = "Close",
}: {
  id: string;

  title: string;
  pinned: boolean;
  onMinimise: () => void;
  onClose: () => void;
  closeHint?: string;
}) {
  return (
    <span className="fw-actions" role="group" aria-label={`${title} window controls`}>
      <button type="button" className="cf-btn cf-btn--icon cf-btn--compact fw-action fw-action-min" aria-label={`Minimise ${title}`} title="Minimise to a tab on the screen edge" onClick={onMinimise}>
        <IconMinus aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`cf-btn cf-btn--icon cf-btn--compact fw-action fw-action-pin${pinned ? " fw-action-on" : ""}`}
        aria-label={`Pin ${title}`}
        aria-pressed={pinned}
        title={pinned ? "Pinned: locked on top and in place. Press to unpin" : "Pin: lock it on top and in place"}
        onClick={() => windowPins.toggle(id)}
      >
        <IconPin filled={pinned} aria-hidden="true" />
      </button>
      <button type="button" className="cf-btn cf-btn--icon cf-btn--compact fw-action fw-action-close" aria-label={`Close ${title}`} title={closeHint} onClick={onClose}>
        <IconClose aria-hidden="true" />
      </button>
    </span>
  );
}
