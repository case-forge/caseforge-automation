"use client";

import { useEffect, useRef, useState } from "react";
import { IconChevronLeft, IconChevronRight } from "./icons";
import { ARROW_LABELS, fetchMatterByNumber, fetchNeighbour, keyDirection, type NeighbourDir } from "@/lib/matterNeighbour";
import type { ClientMatch } from "@/lib/types";

export function MatterNumberArrows({ matterId, onOpenMatter }: { matterId: string; onOpenMatter: (match: ClientMatch) => void }) {
  const [ends, setEnds] = useState<{ matterId: string; prev: boolean; next: boolean }>({ matterId, prev: false, next: false });
  const [busy, setBusy] = useState<NeighbourDir | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState(matterId);
  useEffect(() => setTyped(matterId), [matterId]);
  const atEnd = ends.matterId === matterId ? ends : { prev: false, next: false };
  function go(dir: NeighbourDir) {
    if (!/^\d+$/.test(matterId) || busy || atEnd[dir]) return;
    setBusy(dir);
    setError(null);
    void fetchNeighbour(matterId, dir).then((result) => {
      setBusy(null);
      if (result.kind === "found") onOpenMatter(result.match);
      else if (result.kind === "end") setEnds((current) => ({ ...(current.matterId === matterId ? current : { prev: false, next: false }), matterId, [dir]: true }));
      else setError(result.message);
    });
  }
  function openTyped() {
    const wanted = typed.trim();
    if (!wanted || wanted === matterId || busy) return;
    setBusy("next");
    setError(null);
    void fetchMatterByNumber(wanted).then((result) => {
      setBusy(null);
      if (result.kind === "found") onOpenMatter(result.match);
      else {
        setError(result.kind === "error" ? result.message : `No client numbered ${wanted}`);
        setTyped(matterId);
      }
    });
  }

  const goRef = useRef(go);
  useEffect(() => {
    goRef.current = go;
  });

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const dir = keyDirection(event);
      if (!dir) return;
      event.preventDefault();
      goRef.current(dir);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!/^\d+$/.test(matterId)) return null;
  const arrow = (dir: NeighbourDir) => {
    const Icon = dir === "prev" ? IconChevronLeft : IconChevronRight;
    const label = atEnd[dir] ? ARROW_LABELS[dir].end : ARROW_LABELS[dir].title;
    return (
      <button
        type="button"
        className="edit-button header-flag-toggle matter-number-arrow"
        title={`${label} (${dir === "prev" ? "[" : "]"})`}
        aria-label={label}
        disabled={atEnd[dir] || busy !== null}
        onClick={() => go(dir)}
      >
        <Icon className="header-flag-toggle-icon" aria-hidden="true" />
      </button>
    );
  };
  return (
    <span className="matter-number-arrows" role="group" aria-label="Client number">
      <label className="matter-number-label" htmlFor="matter-number-input">Client no.</label>
      {arrow("prev")}
      <input
        id="matter-number-input"
        className="matter-number-current"
        type="text"
        inputMode="numeric"
        pattern="[0-9]*"
        autoComplete="off"
        value={typed}
        title="Type a client number and press Enter"
        onChange={(event) => setTyped(event.target.value.replace(/\D/g, ""))}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            openTyped();
          } else if (event.key === "Escape") {
            setTyped(matterId);
            setError(null);
          }
        }}
        onBlur={() => setTyped(matterId)}
        size={Math.max(4, typed.length)}
      />
      {arrow("next")}
      {error && <span className="matter-number-error" role="alert">{error}</span>}
    </span>
  );
}
