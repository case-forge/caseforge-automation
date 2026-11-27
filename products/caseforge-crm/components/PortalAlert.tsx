"use client";

import { useEffect, useState } from "react";
import { PORTAL_URL } from "@/lib/types";
import { useModalFocus } from "@/lib/modalFocus";
import { DialogClose } from "./DialogClose";

interface PortalCourts {
  courts: string[];
  court: string;
}

export function PortalAlert({ matterId }: { matterId: string }) {
  const [data, setData] = useState<PortalCourts | null>(null);
  const [listOpen, setListOpen] = useState(false);

  useEffect(() => {
    let live = true;
    fetch(`/api/portal-courts?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" })
      .then(async (res) => (res.ok ? ((await res.json()) as PortalCourts) : Promise.reject(new Error("bad"))))
      .then((body) => live && setData(body))
      .catch(() => live && setData({ courts: [], court: "" }));
    return () => {
      live = false;
    };
  }, [matterId]);

  const court = data?.court || "This court";
  return (
    <section className="portal-alert" role="status" aria-label="Portal case">
      <span className="portal-alert-icon" aria-hidden="true">
        !
      </span>
      <p className="portal-alert-text">
        {court} only takes applications through HMCTS Access.{" "}
        <button type="button" className="cf-btn cf-btn--link portal-alert-list" aria-haspopup="dialog" onClick={() => setListOpen(true)}>
          See list
        </button>
        . For FL401/C100, attach witness statement, draft orders and notice of acting as supporting evidence.{" "}
        <a className="cf-btn cf-btn--primary cf-btn--small portal-alert-open" href={PORTAL_URL} target="_blank" rel="noopener noreferrer">
          Open portal
        </a>
      </p>
      {listOpen && <PortalCourtList courts={data?.courts ?? []} onClose={() => setListOpen(false)} />}
    </section>
  );
}

function PortalCourtList({ courts, onClose }: { courts: string[]; onClose: () => void }) {
  const dialogRef = useModalFocus<HTMLDivElement>(true);
  return (
    <div className="new-client-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="new-client-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="portal-courts-title"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <DialogClose onClose={onClose} />
        <h2 id="portal-courts-title">Portal-only courts</h2>
        {courts.length ? (
          <ul className="portal-court-list">
            {courts.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        ) : (
          <p>The list could not be loaded.</p>
        )}
      </div>
    </div>
  );
}
