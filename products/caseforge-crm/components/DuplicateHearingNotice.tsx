"use client";

import { useEffect, useMemo, useState } from "react";
import { formatDateShort, formatTime12, isValidIsoDate } from "@/lib/hearings";
import type { Hearing, HearingFormValues } from "@/lib/hearings";
import { duplicateMessage, duplicateTarget, findDuplicateHearings } from "@/lib/hearingActions";
import { fetchHearings, isAbort } from "@/lib/hearingsClient";

const LOOKUP_DELAY_MS = 350;

export function DuplicateHearingNotice({
  form,
  known,
  onEditExisting,
}: {
  form: Pick<HearingFormValues, "case_ref" | "matter_id" | "hearing_date" | "hearing_time">;
  known?: Hearing[];
  onEditExisting?: (hearing: Hearing) => void;
}) {
  const [fetched, setFetched] = useState<{ date: string; hearings: Hearing[] } | null>(null);
  const date = isValidIsoDate(form.hearing_date) ? form.hearing_date : "";
  const hasKey = form.case_ref.trim() !== "" || form.matter_id.trim() !== "";

  useEffect(() => {
    if (!date || !hasKey) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchHearings(date, date, controller.signal)
        .then((body) => setFetched({ date, hearings: body.hearings }))
        .catch((err: unknown) => {
          if (!isAbort(err)) setFetched(null);
        });
    }, LOOKUP_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [date, hasKey]);

  const matches = useMemo(() => {
    const byId = new Map<number, Hearing>();
    for (const h of known ?? []) byId.set(h.hearing_id, h);
    if (fetched && fetched.date === date) for (const h of fetched.hearings) byId.set(h.hearing_id, h);
    return findDuplicateHearings([...byId.values()], form);
  }, [known, fetched, date, form]);

  const target = duplicateTarget(matches);
  if (!target) return null;
  const others = (matches.exact ? [matches.exact, ...matches.nearby] : matches.nearby).filter((h) => h.hearing_id !== target.hearing_id);
  return (
    <section className="hearing-duplicate-box" role="status" aria-label="This hearing may already exist">
      <p className="hearing-duplicate-text">{duplicateMessage(matches)}</p>
      <p className="hearing-duplicate-what">
        {formatDateShort(target.hearing_date)}, {formatTime12(target.hearing_time)}
        {target.court ? ` - ${target.court}` : ""}
        {others.length ? ` (and ${others.length} more that day)` : ""}
      </p>
      {onEditExisting && (
        <div className="hearing-actions">
          <button type="button" className="cf-btn cf-btn--primary" onClick={() => onEditExisting(target)}>
            Edit the existing hearing
          </button>
        </div>
      )}
    </section>
  );
}
