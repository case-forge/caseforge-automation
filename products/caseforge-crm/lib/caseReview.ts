"use client";

import { useEffect, useState } from "react";
import type { CaseReview, CaseReviewAnswer, CaseReviewFormKey } from "./caseReviewTypes";

async function readError(res: Response, fallback: string): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw new Error(typeof body?.error === "string" && body.error ? body.error : fallback);
}

function query(matterId: string, reviewDate: string, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams({ matter_id: matterId, ...extra });
  if (reviewDate) params.set("review_date", reviewDate);
  return params.toString();
}

export async function fetchCaseReview(matterId: string, reviewDate = ""): Promise<CaseReview> {
  const res = await fetch(`/api/case-review?${query(matterId, reviewDate)}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "Could not load the case review.");
  return res.json();
}

export async function saveCaseReview(matterId: string, reviewDate: string, answers: Record<string, CaseReviewAnswer>): Promise<CaseReview> {
  const res = await fetch("/api/case-review/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ matter_id: matterId, review_date: reviewDate, answers }),
  });
  if (!res.ok) return readError(res, "The review was not saved.");
  return res.json();
}

export async function downloadCaseReviewForm(matterId: string, form: CaseReviewFormKey, reviewDate: string): Promise<string> {
  const res = await fetch(`/api/case-review/export?${query(matterId, reviewDate, { form })}`, { cache: "no-store" });
  if (!res.ok) return readError(res, "The Word form could not be made.");
  const named = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "");
  const filename = named?.[1] ?? `${form === "review" ? "File-Review" : "File-Summary-Sheet"}.docx`;
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return filename;
}

export function useCaseReview(matterId: string): { data: CaseReview | null; error: string; setData: (a: CaseReview) => void; setError: (e: string) => void } {
  const [data, setData] = useState<CaseReview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchCaseReview(matterId)
      .then((a) => {
        if (!cancelled) {
          setData(a);
          setError("");
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the case review.");
      });
    return () => {
      cancelled = true;
    };
  }, [matterId]);

  return { data, error, setData, setError };
}
