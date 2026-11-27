"use client";

import { IconClose } from "./icons";

export function DialogClose({ onClose }: { onClose: () => void }) {
  return (
    <button type="button" className="cf-btn cf-btn--icon dialog-close" aria-label="Close" title="Close" data-dialog-close="" onClick={onClose}>
      <IconClose aria-hidden="true" />
    </button>
  );
}
