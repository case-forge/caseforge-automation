"use client";

import { IconChevronDown, IconChevronRight } from "./icons";
import { useState } from "react";
import { httpsOnly, miles, type NearestAnswer } from "@/lib/nearest";
import { addressLinesOfText } from "@/lib/types";

export function NearestHelp({ matterId }: { matterId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [answer, setAnswer] = useState<NearestAnswer | null>(null);
  const [error, setError] = useState("");

  function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (!next || answer) return;
    void fetch(`/api/clients/nearest?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" })
      .then(async (res) => ({ ok: res.ok, body: await res.json().catch(() => ({})) }))
      .then(({ ok, body }) => {
        if (!ok) setError(String(body.error ?? "Nearest court and chambers could not be found."));
        else setAnswer(body as NearestAnswer);
      })
      .catch(() => setError("Nearest court and chambers could not be found."));
  }

  return (
    <section className="nearest-help">
      <h3 className="detail-section-title">
        <button type="button" className="cf-btn cf-btn--link nearest-help-toggle" aria-expanded={expanded} onClick={toggle}>
          Nearest court and chambers {expanded ? <IconChevronDown aria-hidden="true" /> : <IconChevronRight aria-hidden="true" />}
        </button>
      </h3>
      {expanded && (
        <div className="nearest-help-body">
          {error && <p className="client-edits-error" role="alert">{error}</p>}
          {!answer && !error && <p className="nearest-help-muted">Looking up…</p>}
          {answer && !answer.ok && <p className="nearest-help-muted">{answer.message}</p>}
          {answer && answer.ok && (
            <>
              <p className="nearest-help-muted">
                Based on the client&apos;s postcode area ({answer.area}), measured from the area&apos;s centre: for choosing, not exact.
              </p>
              <h4>Nearest court</h4>
              {answer.court ? (
                <p>
                  {httpsOnly(answer.court.url) ? (
                    <a href={httpsOnly(answer.court.url) ?? undefined} target="_blank" rel="noopener noreferrer">{answer.court.name}</a>
                  ) : (
                    answer.court.name
                  )}
                  {miles(answer.court.distance_miles) && ` · ${miles(answer.court.distance_miles)}`}
                  {addressLinesOfText(answer.court.address).map((line, i) => <span className="nearest-help-line" key={i}>{line}</span>)}
                  {answer.court.family_emails.length > 0 && <span className="nearest-help-line">{answer.court.family_emails.join(", ")}</span>}
                </p>
              ) : (
                <p className="nearest-help-muted">{answer.court_error}</p>
              )}
              <h4>
                5 nearest chambers{answer.chambers_measured_from ? ` to ${answer.chambers_measured_from}` : ""}
              </h4>
              {answer.chambers.length > 0 ? (
                <ol className="nearest-help-list">
                  {answer.chambers.map((c) => (
                    <li key={`${c.name}-${c.email}`}>
                      {httpsOnly(c.website) ? (
                        <a href={httpsOnly(c.website) ?? undefined} target="_blank" rel="noopener noreferrer">{c.name}</a>
                      ) : (
                        c.name
                      )}
                      {miles(c.distance_miles) && ` · ${miles(c.distance_miles)}`}
                      {(c.email || c.phone) && <span className="nearest-help-line">{[c.email, c.phone].filter(Boolean).join(" · ")}</span>}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="nearest-help-muted">{answer.chambers_error}</p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
