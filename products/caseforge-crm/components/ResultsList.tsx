"use client";

import { WAITING_LISTS } from "@/lib/waiting";
import fuzzysort from "fuzzysort";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { ClientMatch, FieldReviewFlag } from "@/lib/types";
import {
  ORDER_TYPE_LABELS,
  pillFlagsToShow,
  concludedStatus,
  isDeleteLaterFolder,
  hasC8,
  matchKey,
  matchedViaOf,
  orderTypeTagsOf,
  referenceGroupsOf,
  shortNameOf,
} from "@/lib/types";
import { fetchMatterFlagsBatch, knownMatterFlags } from "@/lib/matterFlagsFetch";
import { missingReferralFormOf, reviewReasonOf } from "@/lib/fieldReviewQueue";
import { isNewClient } from "@/lib/newClient";
import { StatusFlagPill } from "./StatusFlagPill";
import { CallerIcons } from "./CallerTagBadge";
import { SameNameHint, SameNameSuffix } from "./SameNameLabel";
import { companyReferenceOf } from "@/lib/sameName";
import { caseLabelsFor } from "@/lib/caseLabel";

export function highlightName(name: string, query: string): ReactNode {
  const trimmed = query.trim();
  if (!trimmed) return name;
  const result = fuzzysort.single(trimmed, name);
  if (!result) return name;
  return result.highlight((match, i) => <mark key={i}>{match}</mark>);
}

interface ResultsListProps {
  results: ClientMatch[];
  count: number;
  loading: boolean;
  error: string | null;
  query: string;

  listSource?: string | null;

  reviewFlagsByMatter?: Record<string, FieldReviewFlag[]>;
  selectedKey: string | null;
  onSelect: (match: ClientMatch, key: string) => void;

  onLoadMore?: () => void;
  loadingMore?: boolean;
}

function usePillFlags(results: ClientMatch[]): Record<string, Record<string, boolean>> {
  const [fetched, setFetched] = useState<Record<string, Record<string, boolean>>>({});
  const matterIds = useMemo(() => results.map((r) => (r.matter_id != null ? String(r.matter_id) : "")).filter(Boolean), [results]);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (matterIds.length === 0) return;

    void fetchMatterFlagsBatch(matterIds).then((flags) => {
      if (mounted.current) setFetched((prev) => mergeFlags(prev, flags));
    });
  }, [matterIds]);

  return { ...fetched, ...knownMatterFlags(matterIds) };
}

export function mergeFlags(prev: Record<string, Record<string, boolean>>, answer: Record<string, Record<string, boolean>>): Record<string, Record<string, boolean>> {
  return Object.keys(answer).length === 0 ? prev : { ...prev, ...answer };
}

const EMPTY_LIST_MESSAGES: Record<string, string> = {
  ...Object.fromEntries(WAITING_LISTS.map(({ label, empty }) => [label, empty])),
  "Frequent callers": "No frequent callers right now.",
  "Recently viewed": "No client recently viewed.",
  Transferred: "No transferred clients right now.",
  "Dropped out": "No one has dropped out right now.",
  Flagged: "No flagged clients right now.",
  Starred: "No starred clients right now.",
  Concluded: "No concluded matters right now.",
  "To check": "Nothing to check right now.",
};

export function emptyListMessage(listSource: string): string {
  return EMPTY_LIST_MESSAGES[listSource] ?? `No one is ${listSource.toLowerCase()} right now.`;
}

export function ResultsList({
  results,
  count,
  loading,
  error,
  query,
  listSource,
  reviewFlagsByMatter,
  selectedKey,
  onSelect,
  onLoadMore,
  loadingMore = false,
}: ResultsListProps) {
  const pillFlags = usePillFlags(results);

  const caseLabels = useMemo(() => caseLabelsFor(results), [results]);
  const sentinelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || !onLoadMore || loadingMore || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) onLoadMore();
    }, { rootMargin: "200px" });
    observer.observe(node);
    return () => observer.disconnect();
  }, [onLoadMore, loadingMore, results.length]);

  if (!listSource && query.trim().length < 2) {
    return (
      <div className="results-pane">
        <p className="results-empty">Type 2+ characters to search.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="results-pane">
        <p className="results-empty" role="alert">{error}</p>
      </div>
    );
  }

  if (loading && results.length === 0) {
    return (
      <div className="results-pane">
        <p className="results-empty">Searching…</p>
      </div>
    );
  }

  if (!loading && results.length === 0) {
    return (
      <div className="results-pane">
        <p className="results-empty">
          {listSource ? emptyListMessage(listSource) : "No matches. An empty result is not proof the client doesn’t exist - a referral not yet onboarded won’t appear here."}
        </p>
      </div>
    );
  }

  return (
    <div className="results-pane">
      <p className="results-count">
        {listSource ? `${listSource}: ${count} client${count === 1 ? "" : "s"}${onLoadMore || results.length < count ? ` (showing ${results.length})` : ""}` : `${count} match${count === 1 ? "" : "es"}`}
        {loading ? " - searching..." : ""}
      </p>
      {results.map((match, index) => {
        const key = matchKey(match, index);
        const matterId = match.matter_id != null ? String(match.matter_id) : "";
        const reviewReason = reviewFlagsByMatter ? reviewReasonOf(reviewFlagsByMatter[matterId]) : null;
        const noReferralForm = reviewFlagsByMatter ? missingReferralFormOf(reviewFlagsByMatter[matterId]) : false;
        const matchedVia = matchedViaOf(match);
        const concluded = concludedStatus(match);
        const orderTags = orderTypeTagsOf(match);
        const flags = pillFlags[matterId] ?? {};

        const refs = referenceGroupsOf(match);

        const refLine = [...refs.court, ...refs.company].join(" · ") || match.case_reference || "";
        const caseLabel = matterId ? caseLabels.get(matterId) : undefined;
        return (

          <div
            key={key}
            role="button"
            tabIndex={0}
            className="result-card"
            data-active={key === selectedKey}
            onClick={() => onSelect(match, key)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(match, key);
              }
            }}
          >
            <p className="result-card-name">
              {highlightName(shortNameOf(match), query)}
              <SameNameSuffix row={match} />
              <CallerIcons flags={flags} />
              {isNewClient(match) && <span className="result-card-new">New</span>}
              {hasC8(match) && <span className="result-card-c8">C8</span>}
              {concluded && <span className="result-card-concluded">Concluded</span>}
              {isDeleteLaterFolder(match) && (
                <span className="result-card-to-delete" title="Filed in a Delete Later folder">TO DELETE</span>
              )}
              { }
              {String(match.client_role ?? "").trim().toLowerCase() === "respondent" && (
                <span className="result-card-respondent">Respondent</span>
              )}
              {pillFlagsToShow(flags, orderTags.length > 0).map((flag) => (
                <StatusFlagPill key={flag.name} flag={flag} className="result-card-status-flag" plainTitle={flag.label} />
              ))}
            </p>
            { }
            <SameNameHint row={{ ...match, company_reference: companyReferenceOf(match.extra) }} />
            {caseLabel && (
              <p className="result-card-case-label" title={caseLabel}>
                {caseLabel}
              </p>
            )}
            {orderTags.length > 0 && (
              <p className="result-card-order-tags">
                {orderTags.map((code) => (
                  <span key={code} className="result-card-order-tag" title={ORDER_TYPE_LABELS[code]}>
                    {code}
                  </span>
                ))}
              </p>
            )}
            {typeof match.extra?.["flag_reason"] === "string" && match.extra["flag_reason"] && (
              <p className="result-card-matched-via result-card-review-reason" style={{ whiteSpace: "pre-line" }}>
                {String(match.extra["flag_reason"])}
              </p>
            )}
            {refLine && <p className="result-card-meta">{refLine}</p>}
            {reviewReason ? (
              <p className="result-card-matched-via result-card-review-reason">{reviewReason}</p>
            ) : (
              !noReferralForm && matchedVia && <p className="result-card-matched-via">Matched via: {matchedVia}</p>
            )}
            {noReferralForm && (
              <p className="result-card-matched-via result-card-review-reason result-card-review-reason--red">Missing referral form</p>
            )}
          </div>
        );
      })}
      {onLoadMore && (
        <div ref={sentinelRef} className="results-more" aria-live="polite">
          {loadingMore ? "Loading more…" : ""}
        </div>
      )}
    </div>
  );
}
