import type { ReactNode } from "react";
import { boardLinkTarget } from "@/lib/boardLinks";

export function BoardDateLink({ href, columnKey, children }: { href: string; columnKey: string; children: ReactNode }) {
  if (!href) return <>{children}</>;
  return (
    <a className="board-date-link" href={href} target="_blank" rel="noopener noreferrer">
      {children}
      <span className="sr-only"> (opens {boardLinkTarget(columnKey)} in a new tab)</span>
    </a>
  );
}
