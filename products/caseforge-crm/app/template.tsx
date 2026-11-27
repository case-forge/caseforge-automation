import type { ReactNode } from "react";
import { MinimisedTabs } from "@/components/MinimisedTabs";
import { DockGhost, SnapPreview } from "@/components/SnapPreview";

export default function Template({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <MinimisedTabs />
      <SnapPreview />
      <DockGhost />
    </>
  );
}
