"use client";

import { useEffect, useState } from "react";
import { linkableMatterId } from "@/lib/hearings";
import type { Hearing, MatterSuggestion } from "@/lib/hearings";
import { fetchMatterSuggestions, isAbort, linkHearing, searchClients } from "@/lib/hearingsClient";
import type { HearingLinkResponse } from "@/lib/hearings";
import type { ClientMatch } from "@/lib/types";
import { ClearableSearch } from "./ClearableSearch";

const SEARCH_DEBOUNCE_MS = 300;

export function LinkToClient({
  hearing,
  onLinked,
  onError,
}: {
  hearing: Hearing;
  onLinked: (result: HearingLinkResponse, clientName: string) => void;
  onError: (message: string) => void;
}) {
  const [suggestions, setSuggestions] = useState<MatterSuggestion[] | null>(null);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ClientMatch[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setSuggestions(null);
    setSuggestError(null);
    fetchMatterSuggestions(hearing.hearing_id, controller.signal)
      .then((body) => setSuggestions(body.suggestions))
      .catch((err: unknown) => {
        if (isAbort(err)) return;
        setSuggestError(err instanceof Error ? err.message : "Could not load suggestions");
      });
    return () => controller.abort();
  }, [hearing.hearing_id]);

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setResults(null);
      setSearchError(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      setSearchError(null);
      searchClients(text, controller.signal)
        .then((body) => setResults(body.results))
        .catch((err: unknown) => {
          if (isAbort(err)) return;
          setResults(null);
          setSearchError(err instanceof Error ? err.message : "Search failed");
        })
        .finally(() => setSearching(false));
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  async function link(matterId: number, clientName: string) {
    const number = hearing.case_ref.trim() || "this hearing";
    const client = clientName.trim() || `matter ${matterId}`;
    const ok = window.confirm(
      `Link ${number} to ${client}?\n\nEvery unlinked hearing with the same case number is linked too, and the number is remembered on ${client} so future emails link themselves.`,
    );
    if (!ok) return;
    setBusy(true);
    try {
      onLinked(await linkHearing(hearing.hearing_id, matterId), client);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not link the hearing");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="hearing-link" aria-label="Link to client">
      <h3 className="detail-section-title">Link to client</h3>
      <p className="hearing-muted">
        No client is recorded for {hearing.case_ref.trim() || "this hearing"}. Linking it also links the other hearings with the same case number.
      </p>

      {suggestions === null && !suggestError && <p className="hearing-muted">Looking for likely clients...</p>}
      {suggestError && <p className="hearing-form-error" role="alert">{suggestError}</p>}
      {suggestions !== null && suggestions.length > 0 && (
        <div className="hearing-link-group">
          <p className="hearing-link-heading">Suggested (a guess from the names, so check it)</p>
          <ul className="hearing-link-list">
            {suggestions.map((s) => (
              <li key={s.matter_id}>
                <button type="button" className="cf-btn cf-btn--neutral hearing-link-choice" disabled={busy} onClick={() => void link(s.matter_id, s.client_name)}>
                  <span className="hearing-link-name">{s.client_name || `Matter ${s.matter_id}`}</span>
                  <span className="hearing-link-why">
                    Suggested{s.exact ? " (exact name match)" : ""}
                    {s.matched_on ? `, matched on ${s.matched_on}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {suggestions !== null && suggestions.length === 0 && !suggestError && (
        <p className="hearing-muted">No likely clients found from the names. Search for the client below.</p>
      )}

      <div className="hearing-link-group">
        <label htmlFor="hearing-link-search" className="hearing-link-heading">
          Search all clients
        </label>
        <ClearableSearch
          id="hearing-link-search"
          className="edit-input"
          value={query}
          placeholder="Name, court reference, email or phone"
          autoComplete="off"
          disabled={busy}
          clearLabel="Clear the search"
          onValueChange={setQuery}
        />
        {searching && <p className="hearing-muted">Searching...</p>}
        {searchError && <p className="hearing-form-error" role="alert">{searchError}</p>}
        {results !== null && !searching && results.length === 0 && <p className="hearing-muted">No clients found.</p>}
        {results !== null && results.length > 0 && (
          <ul className="hearing-link-list">
            {results.map((row, index) => {
              const matterId = linkableMatterId(row.matter_id);
              const name = (row.client_name ?? "").trim() || "Unnamed client";
              return (
                <li key={matterId ?? `row-${index}`}>
                  <button
                    type="button"
                    className="cf-btn cf-btn--neutral hearing-link-choice"
                    disabled={busy || matterId === null}
                    onClick={() => matterId !== null && void link(matterId, name)}
                  >
                    <span className="hearing-link-name">{name}</span>
                    <span className="hearing-link-why">
                      {matterId === null
                        ? "Cannot link: no matter record yet"
                        : [row.case_reference, row.matter_name].filter(Boolean).join(" - ") || `Matter ${matterId}`}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
