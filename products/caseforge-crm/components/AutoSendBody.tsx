"use client";

import { useState } from "react";
import { AutoSentPanel } from "./AutoSentPanel";
import type { AutoSendState } from "@/lib/autoSend";

export function AutoSendBody() {
  const [tab, setTab] = useState<AutoSendState>("leaving_soon");
  return <AutoSentPanel tab={tab} onTab={setTab} />;
}
