"use client";

import { countBadge } from "@/lib/hearingsHost";

export function CountBadge({
  count,
  label,
  className = "",
  tone = "accent",
  decorative = false,
}: {
  count: number;
  label: string;
  className?: string;

  tone?: "accent" | "solid";

  decorative?: boolean;
}) {
  const text = countBadge(count);
  if (!text) return null;
  return (
    <span
      className={`window-count${tone === "accent" ? "" : ` window-count--${tone}`} ${className}`.trim()}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": `${count} ${label}`, title: `${count} ${label}` })}
    >
      {text}
    </span>
  );
}
