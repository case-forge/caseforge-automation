"use client";

import { useEffect, useState } from "react";

interface MatterCourtAnswer {
  court: string;
  source: string;
}

export function MatterCourt({ matterId }: { matterId: string }) {
  const [answer, setAnswer] = useState<MatterCourtAnswer | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setAnswer(null);
    setFailed(false);
    fetch(`/api/clients/matter-court?matter_id=${encodeURIComponent(matterId)}`, { cache: "no-store" })
      .then(async (res) => (res.ok ? ((await res.json()) as MatterCourtAnswer) : Promise.reject(new Error("bad"))))
      .then((body) => live && setAnswer(body))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [matterId]);

  if (failed) return null;
  const court = answer?.court || "";
  return (
    <div className="detail-field">
      <div className="detail-field-head">
        <p className="detail-field-label">Initial court</p>
      </div>
      <div className="detail-field-value-row">
        <p className={`detail-field-value${answer && !court ? " detail-field-value--empty" : ""}`}>
          {answer ? court || "Not recorded" : "Loading…"}
        </p>
      </div>
    </div>
  );
}
