"use client";

import { useState } from "react";
import { conflictNotice, runConflictCheck, useConflictCheck } from "@/lib/conflictCheck";
import type { ConflictMatch } from "@/lib/conflictCheck";
import type { CaseReviewAnswer } from "@/lib/caseReviewTypes";
import { longDate } from "@/lib/caseReviewTypes";

const STRENGTH_LABEL: Record<ConflictMatch["strength"], string> = { strong: "Strong", possible: "Possible", weak: "Weak" };

function MatchLine({ match }: { match: ConflictMatch }) {
  const matter = match.other_reference || `matter ${match.other_matter_id}`;
  const where = `${matter}${match.other_closed ? ", closed" : ""}`;
  return (
    <li className="aud-conflict-match" data-strength={match.strength}>
      <span className="aud-conflict-strength">{STRENGTH_LABEL[match.strength]}</span>
      <span className="aud-conflict-what">
        {match.this_is} may be {match.other_name || "a person of the same name"}
        {", "}
        <em>{match.that_is.toLowerCase()}</em> ({where}).
        {match.direction === "client_is_opponent" && match.other_client ? ` Our client there: ${match.other_client}.` : ""}
      </span>
      <small className="aud-conflict-why">Matched on: {match.reasons.join(", ")}.</small>
    </li>
  );
}

export function ConflictCheckPanel({ matterId, answers }: { matterId: string; answers: Record<string, CaseReviewAnswer> }) {
  const { check, error, setCheck, setError } = useConflictCheck(matterId);
  const [busy, setBusy] = useState(false);
  const notice = conflictNotice(check, answers);
  const loading = !check && !error;

  async function run() {
    if (busy || loading) return;
    setBusy(true);
    try {
      setCheck(await runConflictCheck(matterId));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The conflict check could not be run.");
    } finally {
      setBusy(false);
    }
  }

  const reason = busy ? "Checking." : "";
  return (
    <section className="aud-conflict" aria-label="Conflict of interest check" data-level={notice?.level ?? "info"}>
      <div className="aud-conflict-head">
        <h3 className="aud-form-title">Conflict of interest check</h3>
        <span className="cf2-action">
          <button type="button" className="cf-btn cf-btn--primary cf2-run" disabled={reason !== "" || loading} title={reason || (loading ? "Loading the conflict check." : undefined)} onClick={() => void run()}>
            {busy ? "Checking..." : check?.run ? "Run it again" : "Run the conflict check"}
          </button>
          {reason && !busy && <small className="cf2-reason">{reason}</small>}
        </span>
      </div>

      {loading && <p className="cf2-note">Loading the conflict check...</p>}
      {notice && (
        <p className="aud-conflict-notice" data-level={notice.level} role={notice.level === "alert" ? "alert" : "status"}>
          <strong>{notice.headline}</strong>
          {notice.lines.map((line) => (
            <span key={line} className="aud-conflict-line">
              {line}
            </span>
          ))}
        </p>
      )}
      {check?.run && check.matches.length > 0 && (
        <ul className="aud-conflict-matches">
          {check.matches.map((m) => (
            <MatchLine key={`${m.direction}:${m.other_matter_id}:${m.this_is}`} match={m} />
          ))}
        </ul>
      )}
      {check?.run && check.held_back > 0 && <p className="cf2-note">{check.held_back === 1 ? "1 weaker match is not listed." : `${check.held_back} weaker matches are not listed.`}</p>}
      {check?.run && (
        <p className="cf2-note">
          Run by {check.run_by} on {longDate(check.run_utc)}. Compared with {check.compared.clients ?? 0} other clients and {check.compared.parties ?? 0} other
          parties on file. This checks names and contact details on record, so a person not recorded yet will not appear. It does not answer the conflict
          row on the forms below: that answer is yours.
        </p>
      )}
      {error && <p className="cf2-error" role="alert">{error}</p>}
    </section>
  );
}
