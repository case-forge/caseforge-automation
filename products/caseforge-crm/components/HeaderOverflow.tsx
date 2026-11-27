"use client";

import { createContext, useContext, useLayoutEffect, useMemo, useState } from "react";
import type { ReactNode, Ref, RefObject } from "react";
import { createPortal } from "react-dom";
import { HEADER_ITEMS, fitHeaderItems, sameItems } from "@/lib/headerOverflow";
import type { HeaderItemId, HeaderWidths } from "@/lib/headerOverflow";

type OverflowState = { collapsed: readonly HeaderItemId[]; slot: HTMLElement | null };

const OverflowContext = createContext<OverflowState>({ collapsed: [], slot: null });
const ItemContext = createContext<{ id: HeaderItemId; collapsed: boolean; slot: HTMLElement | null } | null>(null);

export function HeaderOverflowProvider({ value, children }: { value: OverflowState; children: ReactNode }) {
  return <OverflowContext.Provider value={value}>{children}</OverflowContext.Provider>;
}

export function useHeaderOverflow(actionsRef: RefObject<HTMLElement | null>, hidden: readonly HeaderItemId[] = []): readonly HeaderItemId[] {
  const [collapsed, setCollapsed] = useState<readonly HeaderItemId[]>([]);

  const hiddenKey = hidden.join(",");

  useLayoutEffect(() => {
    const actions = actionsRef.current;
    if (!actions || typeof ResizeObserver === "undefined") return;

    const widthOf = (el: Element | null) => (el ? Math.ceil(el.getBoundingClientRect().width) : 0);

    const measure = () => {
      const widths: HeaderWidths = {};
      for (const wrapper of actions.querySelectorAll<HTMLElement>("[data-header-item]")) {
        widths[wrapper.dataset.headerItem as HeaderItemId] = widthOf(wrapper.querySelector("[data-header-measure]"));
      }
      let reserved = 0;
      for (const fixed of actions.querySelectorAll("[data-header-fixed]")) reserved += widthOf(fixed);
      const next = fitHeaderItems({
        available: Math.floor(actions.getBoundingClientRect().width),
        reserved,
        gap: parseFloat(getComputedStyle(actions).columnGap) || 0,
        widths,
        hidden: hiddenKey ? (hiddenKey.split(",") as HeaderItemId[]) : [],
      });
      setCollapsed((prev) => (sameItems(prev, next) ? prev : next));
    };

    const sizes = new ResizeObserver(measure);
    const watch = () => {
      sizes.disconnect();
      sizes.observe(actions);
      for (const el of actions.querySelectorAll("[data-header-measure], [data-header-fixed]")) sizes.observe(el);
    };

    const changes = new MutationObserver(() => {
      watch();
      measure();
    });
    watch();
    measure();
    changes.observe(actions, { childList: true, subtree: true });
    return () => {
      sizes.disconnect();
      changes.disconnect();
    };
  }, [actionsRef, hiddenKey]);

  return collapsed;
}

export function HeaderItem({ id, children }: { id: HeaderItemId; children: ReactNode }) {
  const { collapsed, slot } = useContext(OverflowContext);
  const isCollapsed = collapsed.includes(id);
  const value = useMemo(() => ({ id, collapsed: isCollapsed, slot }), [id, isCollapsed, slot]);
  return (
    <div className="header-item" data-header-item={id} data-collapsed={isCollapsed ? "true" : undefined}>
      <ItemContext.Provider value={value}>{children}</ItemContext.Provider>
    </div>
  );
}

export function HeaderOverflowEntry({
  ref,
  icon,
  label,
  ariaLabel,
  count = 0,
  tone,
  active,
  complaint,
  expanded,
  onClick,
}: {
  ref?: Ref<HTMLButtonElement>;
  icon: ReactNode;
  label: string;
  ariaLabel: string;
  count?: number;
  tone: string;
  active?: boolean;
  complaint?: boolean;
  expanded: boolean;
  onClick: () => void;
}) {
  const item = useContext(ItemContext);
  if (!item || !item.collapsed || !item.slot) return null;
  return createPortal(
    <button
      ref={ref}
      type="button"
      className="cf-btn cf-btn--flush cf-btn--row app-drawer-item header-overflow-entry"
      style={{ order: HEADER_ITEMS.indexOf(item.id) }}
      aria-haspopup="dialog"
      aria-expanded={expanded}
      aria-label={ariaLabel}
      data-menu-close=""
      onClick={onClick}
    >
      <span className={`header-overflow-tone ${tone}`} data-active={active} data-complaint={complaint}>
        {icon}
        <span className="header-overflow-label">{label}</span>
        {count > 0 && (
          <span className="attention-count" aria-hidden="true">
            {count}
          </span>
        )}
      </span>
    </button>,
    item.slot,
  );
}
