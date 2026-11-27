import { useCallback, useState } from "react";

export type SortDir = "asc" | "desc";
export interface SortState<K extends string> {
  key: K;
  dir: SortDir;
}

export function useSort<K extends string>(initial: SortState<K> | null = null) {
  const [sort, setSort] = useState<SortState<K> | null>(initial);
  const toggle = useCallback((key: K) => {
    setSort((cur) => {
      if (!cur || cur.key !== key) return { key, dir: "asc" };
      if (cur.dir === "asc") return { key, dir: "desc" };
      return null;
    });
  }, []);
  return { sort, toggle };
}

type SortValue = string | number;

export function sortRows<T, K extends string>(rows: T[], sort: SortState<K> | null, value: (row: T, key: K) => SortValue): T[] {
  if (!sort) return rows;
  const sign = sort.dir === "asc" ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, v: value(row, sort.key) }))
    .sort((a, b) => {
      const cmp =
        typeof a.v === "number" && typeof b.v === "number"
          ? a.v - b.v
          : String(a.v).localeCompare(String(b.v), "en-GB", { sensitivity: "base", numeric: true });
      return cmp !== 0 ? sign * cmp : a.index - b.index;
    })
    .map((x) => x.row);
}

export function moneyValue(text: string): number {
  const n = Number.parseFloat(String(text).replace(/[^0-9.-]/g, ""));
  return Number.isFinite(n) ? n : 0;
}

export function billDateValue(text: string): string {
  const s = String(text).trim();
  const dmy = /^(\d{1,2})[./](\d{1,2})[./](\d{2}|\d{4})$/.exec(s);
  if (dmy) {
    const year = dmy[3].length === 2 ? `20${dmy[3]}` : dmy[3];
    return `${year}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
  }
  return s.slice(0, 10);
}
