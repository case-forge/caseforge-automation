"use client";

import { NotificationBoardView } from "./NotificationBoard";
import { ScansView } from "./ScansView";
import { openClientInNewTab } from "@/lib/clientLink";

export function NotificationBoardPage() {
  return <NotificationBoardView onOpenClient={(name, target) => openClientInNewTab(name, target)} />;
}

export function ScansPage() {
  return <ScansView />;
}
