"use client";

import { useCallback, useEffect, useState } from "react";
import { MailBatchCheck } from "@/components/MailControlTab";
import { MailEmailCard } from "@/components/MailEmailCard";
import { MailRoutePicker } from "@/components/MailRoutePicker";
import { backlogLine, decideContext, SAVED_NOTE, type DecideView } from "@/lib/mailReview";

async function getJson(url: string): Promise<{ ok: boolean; body: Record<string, unknown> }> {
  const res = await fetch(url, { cache: "no-store" });
  return { ok: res.ok, body: await res.json().catch(() => ({})) };
}

export function MailReviewTab() {
  const [view, setView] = useState<DecideView | null>(null);
  const [offset, setOffset] = useState(0);
  const [route, setRoute] = useState("");
  const [otherText, setOtherText] = useState("");
  const [logic, setLogic] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    (at: number) =>
      getJson(`/api/mail-review?view=decide&offset=${at}`)
        .then(({ ok, body }) => {
          if (!ok) {
            setError(String(body.error ?? "The emails waiting for a decision could not be loaded."));
            return;
          }
          setView(body as unknown as DecideView);
          setRoute("");
          setOtherText("");
          setLogic("");
          setError("");
        })
        .catch(() => setError("The emails waiting for a decision could not be loaded.")),
    [],
  );

  useEffect(() => {
    void load(0);
  }, [load]);

  async function save() {
    const item = view?.item;
    if (!item || busy || !route || (route === "Other" && !otherText.trim())) return;
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/mail-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "decide", job_id: item.job_id, route, other_text: route === "Other" ? otherText.trim() : "", logic }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(String(body.error ?? "The decision could not be saved."));
        return;
      }
      setNote(SAVED_NOTE);
      await load(offset);
    } catch {
      setError("The decision could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  function skip() {
    const next = view && view.total > 0 ? (offset + 1) % view.total : 0;
    setOffset(next);
    setNote("");
    void load(next);
  }

  const item = view?.item ?? null;
  return (
    <section aria-labelledby="review-heading">
      <h2 id="review-heading" className="review-mail-tab-heading">Review</h2>
      <p className="review-mail-muted">The classifier was not confident about these emails. Please review them.</p>
      {view && <p className="review-mail-muted">{backlogLine(view.total, view.oldest_days)}</p>}
      {error && <p className="new-client-error" role="alert">{error}</p>}
      {note && <p className="review-mail-note" role="status">{note}</p>}
      {view && !item && <p className="review-mail-done">All clear. Thank you.</p>}
      {view?.recent && view.recent.length > 0 && (
        <section aria-labelledby="recent-heading">
          <h3 id="recent-heading" className="review-mail-muted">Routes you chose lately</h3>
          <ul className="review-mail-context">
            {view.recent.map((r) => (
              <li key={`${r.saved_utc}-${r.route}`}>{r.route || "No route"}: {r.plain}</li>
            ))}
          </ul>
        </section>
      )}
      {item && view && (
        <>
          <nav className="review-mail-nav" aria-label="Emails waiting">
            <span>#{item.n} of {item.total}</span>
            <button type="button" className="cf-btn cf-btn--neutral" onClick={skip} disabled={busy || item.total < 2}>Skip to the next</button>
          </nav>
          <MailEmailCard item={item} />
          <ul className="review-mail-context" aria-label="How the classifier got here">
            {decideContext(item).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <form
            className="review-mail-form"
            onSubmit={(event) => {
              event.preventDefault();
              void save();
            }}
          >
            <fieldset disabled={busy}>
              <MailRoutePicker routes={view.routes} value={route} onChange={(r) => { setRoute(r); if (r === "Other" && !otherText) setOtherText(item.applied_other_text ?? ""); }} legend="Where does this go?" name="decide-route" otherText={otherText} onOtherText={setOtherText} />
              <label className="classifier-prompt-comment">
                Notes
                <textarea rows={3} maxLength={2000} value={logic} onChange={(e) => setLogic(e.target.value)} />
              </label>
              <div className="review-mail-actions">
                <button type="submit" className="cf-btn cf-btn--primary" disabled={!route || (route === "Other" && !otherText.trim())}>Save and next</button>
              </div>
            </fieldset>
          </form>
        </>
      )}
      <section aria-labelledby="filed-unsure-heading">
        <h3 id="filed-unsure-heading" className="review-mail-tab-heading">Filed, but the classifier was not sure</h3>
        <MailBatchCheck pool="review" />
      </section>
    </section>
  );
}
