import type { PillFlag } from "@/lib/types";

export function StatusFlagPill({ flag, className, plainTitle }: { flag: PillFlag; className: string; plainTitle?: string }) {
  if (!flag.href) {
    return (
      <span className={className} title={plainTitle}>
        {flag.label}
      </span>
    );
  }
  return (
    <a
      className={`${className} status-flag-link`}
      href={flag.href}
      target="_blank"
      rel="noopener noreferrer"
      title="Open the court's online portal"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      {flag.label}
    </a>
  );
}
