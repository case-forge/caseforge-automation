"use client";

import { useClientEdit } from "./ClientEdits";
import { IconEdit } from "./icons";

const FIELD_SELECTOR = "input, select, textarea";

function firstFieldAfter(heading: Element | null): HTMLElement | null {
  let sibling = heading?.nextElementSibling ?? null;
  while (sibling) {
    const field = sibling.matches(FIELD_SELECTOR) ? sibling : sibling.querySelector(FIELD_SELECTOR);
    if (field instanceof HTMLElement) return field;
    sibling = sibling.nextElementSibling;
  }
  return null;
}

export function SectionEditButton({ section, sectionKey }: { section: string; sectionKey: string }) {
  const ed = useClientEdit();
  if (!ed || ed.editing) return null;
  return (
    <button
      type="button"
      className="cf-btn cf-btn--icon section-edit-button"
      aria-label={`Edit ${section}`}
      title={`Edit ${section}`}
      onClick={() => {
        ed.startEdit();
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            const heading = document.querySelector(`[data-section="${sectionKey}"]`);
            firstFieldAfter(heading)?.focus({ preventScroll: false });
          });
        });
      }}
    >
      <IconEdit aria-hidden="true" />
    </button>
  );
}
