"use client";

import { BannerOffset } from "./BannerOffset";
import { ClassifierPrompt } from "./ClassifierPrompt";
import { WhatsNewPanel } from "./WhatsNew";

export function WidgetLayer() {
  return (
    <>
      <BannerOffset />
      <WhatsNewPanel />
      <ClassifierPrompt />
    </>
  );
}
