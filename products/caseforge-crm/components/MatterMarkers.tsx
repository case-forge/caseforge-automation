"use client";

import { useEffect, useState, type ReactNode } from "react";
import { GRAPH_READ_CACHE_MS, useLazyFetch } from "@/lib/useLazyFetch";
import { markerView } from "@/lib/matterMarkers";
import type { MatterMarker, MatterMarkersResponse } from "@/lib/types";
import { IconCheck } from "./icons";
import { RecordSignedWs } from "./RecordSignedWs";

export const INTRO_FOUND_EVENT = "caseforge:intro-found";

function useMatterMarkers(matterId: string): { markers: MatterMarkersResponse | null; failed: boolean } {
  const { data: markers, failed } = useLazyFetch<MatterMarkersResponse>(
    matterId ? `/api/clients/matter-markers?matter_id=${encodeURIComponent(matterId)}` : null,
    { cacheMs: GRAPH_READ_CACHE_MS },
  );

  useEffect(() => {
    const intro = markers?.intro;
    if (intro?.status === "received" && typeof intro.url === "string" && intro.url.startsWith("https://")) {
      window.dispatchEvent(new CustomEvent(INTRO_FOUND_EVENT, { detail: { matterId, url: intro.url } }));
    }
  }, [markers, matterId]);

  return { markers, failed };
}

function Marker({ label, title, marker, failed, action }: { label: string; title: string; marker: MatterMarker | undefined; failed: boolean; action?: ReactNode }) {
  const view = markerView(marker, failed);
  return (
    <div className="detail-field matter-marker" data-state={view.state}>
      <p className="detail-field-label" title={title}>
        {label}
      </p>
      <p className="matter-marker-value">
        <span className="matter-marker-box" aria-hidden="true">
          {view.state === "received" && <IconCheck width={13} height={13} strokeWidth={3} />}
        </span>
        {view.url ? (
          <a className="matter-marker-link" href={view.url} target="_blank" rel="noopener noreferrer">
            {view.text}
          </a>
        ) : (
          <span>{view.text}</span>
        )}
        {view.state === "missing" && action}
      </p>
    </div>
  );
}

export function MatterMarkers({ matterId }: { matterId: string }) {
  const { markers, failed: fetchFailed } = useMatterMarkers(matterId);
  const failed = fetchFailed || !matterId;

  const [recorded, setRecorded] = useState<MatterMarker | null>(null);
  return (
    <>
      <Marker label="Letter of authority" title="Signed letter of authority, filed by the system when it came back" marker={markers?.loa} failed={failed} />
      <Marker label="1st witness statement" title="The client's signed witness statement (WS PDF in Client's Docs); a Word draft does not count" marker={recorded ?? markers?.initial_ws} failed={failed}
        action={<RecordSignedWs matterId={matterId} onRecorded={(f) => setRecorded({ status: "received", date: f.modified })} />} />
    </>
  );
}
