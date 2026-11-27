"use client";

import { useState } from "react";
import { IconCheck, IconCopy } from "./icons";

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  async function copy(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {

    }
  }

  return (
    <button
      type="button"
      className="cf-btn cf-btn--icon cf-btn--compact"
      aria-label={`Copy ${label ?? text}`}
      title={copied ? "Copied" : "Copy"}
      onClick={copy}
    >
      {copied ? <IconCheck /> : <IconCopy />}
    </button>
  );
}
