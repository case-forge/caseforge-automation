"use client";

import { useCallback, useEffect, useState } from "react";
import { closingLetterDate } from "./lexcelTypes";
import type { Lexcel, LexcelKind, LexcelMakeResult } from "./lexcelTypes";

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

export async function fetchLexcel(matterId: string, { advice = true }: { advice?: boolean } = {}): Promise<Lexcel> {
  const extra = advice ? "" : "&advice=false";
  const res = await fetch(`/api/lexcel?matter_id=${encodeURIComponent(matterId)}${extra}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the Lexcel letters.");
  return res.json();
}

export function useClosingLetterDate(matterId: string): string {
  const [text, setText] = useState("");
  useEffect(() => {
    let cancelled = false;
    setText("");
    fetchLexcel(matterId, { advice: false })
      .then((l) => {
        if (!cancelled) setText(closingLetterDate(l));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [matterId]);
  return text;
}

export async function makeLexcelLetter(matterId: string, kind: LexcelKind, variant?: string): Promise<LexcelMakeResult> {
  const res = await fetch("/api/lexcel/make", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, kind, ...(variant ? { variant } : {}) }),
  });
  if (!res.ok) return readError(res, "The letter was not made.");
  return res.json();
}

export async function setLexcelAuto(matterId: string, resume = false): Promise<{ ok: boolean; message: string }> {
  const res = await fetch("/api/lexcel/auto", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, resume }),
  });
  if (!res.ok) return readError(res, "That did not go through.");
  return res.json();
}

export function useLexcel(matterId: string): { data: Lexcel | null; error: string; setData: (l: Lexcel) => void; refresh: () => void } {
  const [data, setData] = useState<Lexcel | null>(null);
  const [error, setError] = useState("");
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    fetchLexcel(matterId)
      .then((l) => {
        if (!cancelled) {
          setData(l);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the Lexcel letters.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId, nonce]);

  return { data, error, setData, refresh };
}
