"use client";

import { useCallback, useEffect, useState } from "react";
import { MailEmailCard } from "@/components/MailEmailCard";
import { MailRoutePicker } from "@/components/MailRoutePicker";
import { controlSentence, isUndecided, type ControlVerdict, type ControlView } from "@/lib/mailReview";

const VIEW: Record<BatchPool, string> = { control: "control", review: "review-batch" };

async function getJson(url: string): Promise<{ ok: boolean; body: Record<string, unknown> }> {
  const res = await fetch(url, { cache: "no-store" });
  return { ok: res.ok, body: await res.json().catch(() => ({})) };
}

export type BatchPool = "control" | "review";

export function MailBatchCheck({ pool }: { pool: BatchPool }) {
  const [view, setView] = useState<ControlView | null>(null);
  const [disagreeing, setDisagreeing] = useState(false);
  const [route, setRoute] = useState("");
  const [otherText, setOtherText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    (n: number | null) =>
      getJson(`/api/mail-review?view=${VIEW[pool]}${n === null ? "" : `&n=${n}`}`)
        .then(({ ok, body }) => {
          if (!ok) {
            setError(String(body.error ?? "Today's batch could not be loaded."));
            return;
          }
          setView(body as unknown as ControlView);
          setDisagreeing(false);
          setRoute("");
          setOtherText("");
          setError("");
        })
        .catch(() => setError("Today's batch could not be loaded.")),
    [pool],
  );

  useEffect(() => {
    void load(null);
  }, [load]);

  async function answer(verdict: ControlVerdict) {
    const item = view?.item;
    if (!item || !view || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/mail-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "control", date: view.date, job_id: item.job_id, verdict, route: verdict === "disagree" ? route : "", other_text: verdict === "disagree" && route === "Other" ? otherText.trim() : "" }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(String(body.error ?? "The answer could not be saved."));
        return;
      }
      await load(null);
    } catch {
      setError("The answer could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const item = view?.item ?? null;
  const allDone = Boolean(view) && view!.total > 0 && view!.answered >= view!.total;
  return (
    <div data-pool={pool}>
      {view && (
        <p className="review-mail-muted" aria-live="polite">
          {view.total === 0 ? "Nothing to check today." : `Today's batch: ${view.answered} of ${view.total} checked.`}
        </p>
      )}
      {error && <p className="new-client-error" role="alert">{error}</p>}
      {allDone && <p className="review-mail-done">Today&rsquo;s batch is done. Thank you. A new one is drawn tomorrow.</p>}
      {item && view && !allDone && (
        <>
          <MailEmailCard item={item} />
          <section className="review-mail-ask" aria-label="The classifier's answer">
            <p className="review-mail-sentence">{controlSentence(item)}</p>
            {!isUndecided(item.applied_route) && item.model_route && item.model_route !== item.applied_route && (
              <p className="review-mail-muted">The model suggested {item.model_route}; the rules kept {item.applied_destination || item.applied_route}.</p>
            )}
            <fieldset disabled={busy} className="review-mail-ask-actions">
              <legend className="review-mail-sr">Your answer</legend>
              {!isUndecided(item.applied_route) && (
                <button type="button" className="cf-btn cf-btn--primary review-mail-yes" onClick={() => void answer("agree")}>Agree</button>
              )}
              <button type="button" className="cf-btn cf-btn--neutral" aria-expanded={disagreeing || isUndecided(item.applied_route)} onClick={() => setDisagreeing((v) => !v)}>
                {isUndecided(item.applied_route) ? "Choose the route" : "Disagree"}
              </button>
            </fieldset>
            {(disagreeing || isUndecided(item.applied_route)) && (
              <form
                className="review-mail-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (route && !(route === "Other" && !otherText.trim())) void answer("disagree");
                }}
              >
                <fieldset disabled={busy}>
                  <MailRoutePicker routes={view.routes.filter((r) => r !== item.applied_route)} value={route} onChange={setRoute} legend="What is the right route?" name={`${pool}-route`} otherText={otherText} onOtherText={setOtherText} />
                  <div className="review-mail-actions">
                    <button type="submit" className="cf-btn cf-btn--primary" disabled={!route || (route === "Other" && !otherText.trim())}>Save my answer</button>
                  </div>
                </fieldset>
              </form>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export function MailControlTab() {
  return (
    <section aria-labelledby="control-heading">
      <h2 id="control-heading" className="review-mail-tab-heading">Control</h2>
      <p className="review-mail-muted">The classifier was confident about these emails. Check them to see it is working properly.</p>
      <MailBatchCheck pool="control" />
    </section>
  );
}
