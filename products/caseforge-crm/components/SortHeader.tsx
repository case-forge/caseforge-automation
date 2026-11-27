"use client";

import { IconArrowDown, IconArrowUp, IconArrowUpDown } from "./icons";
import type { SortState } from "@/lib/sortRows";

export function SortHeader<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
  className,
}: {
  label: string;
  sortKey: K;
  sort: SortState<K> | null;
  onSort: (key: K) => void;
  className?: string;
}) {
  const active = sort?.key === sortKey ? sort.dir : null;
  return (
    <button
      type="button"
      className={`sort-header${className ? ` ${className}` : ""}`}
      aria-label={`Sort by ${label}${active ? `, currently ${active === "asc" ? "ascending" : "descending"}` : ""}`}
      data-sort={active ?? undefined}
      onClick={() => onSort(sortKey)}
    >
      <span>{label}</span>
      <span className="sort-header-arrow" aria-hidden="true">{active === "asc" ? <IconArrowUp /> : active === "desc" ? <IconArrowDown /> : <IconArrowUpDown />}</span>
    </button>
  );
}
