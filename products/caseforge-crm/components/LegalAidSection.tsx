"use client";

import { useEffect, useState } from "react";
import { fetchLegalAid, legalAidLines, sendForSignature, showSendButton } from "@/lib/legalAid";
import type { LegalAidLine, LegalAidSection as Section } from "@/lib/legalAid";
import { IconCheck } from "./icons";

function Line({ line, children }: { line: LegalAidLine; children?: React.ReactNode }) {
  return (
    <div className="detail-field matter-marker legal-aid-line" data-state={line.ticked ? "received" : "missing"} data-line={line.key}>
      <p className="detail-field-label">{line.label}</p>
      <p className="matter-marker-value">
        <span className="matter-marker-box" aria-hidden="true">
          {line.ticked && <IconCheck width={13} height={13} strokeWidth={3} />}
        </span>
        {line.url ? (
          <a className="matter-marker-link" href={line.url} target="_blank" rel="noopener noreferrer">
            {line.text}
          </a>
        ) : (
          <span>{line.text}</span>
        )}
      </p>
      {line.note && <p className="legal-aid-note">{line.note}</p>}
      {children}
    </div>
  );
}

export function LegalAidSection({ matterId, nino }: { matterId: string; nino?: string | null }) {
  const [section, setSection] = useState<Section | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [askAddress, setAskAddress] = useState(false);

  useEffect(() => {
    if (!matterId) return;
    let cancelled = false;
    fetchLegalAid(matterId)
      .then((body) => !cancelled && setSection(body))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [matterId]);

  async function send(addressChecked: boolean) {
    setBusy(true);
    setMessage("");
    try {
      const result = await sendForSignature(matterId, addressChecked);
      setSection(result.section);
      setMessage(result.message);
      setAskAddress(!result.ok && result.code === "address");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Nothing was made.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h3 className="detail-section-title">Legal aid</h3>
      <div className="detail-grid legal-aid-section">
        <div className="detail-field">
          <div className="detail-field-head">
            <p className="detail-field-label">NI Number</p>
          </div>
          <p className={`detail-field-value${nino ? "" : " detail-field-value--empty"}`}>{nino || "Not on record"}</p>
        </div>
        {failed || !matterId ? (
          <p className="detail-field-value detail-field-value--empty">Couldn&apos;t check</p>
        ) : !section ? (
          <p className="detail-field-value detail-field-value--empty">Checking…</p>
        ) : (
          legalAidLines(section).map((line) => (
            <Line key={line.key} line={line}>
              {line.key === "signature" && showSendButton(section) && (
                <div className="legal-aid-actions">
                  <button type="button" className="cf-btn cf-btn--primary cf2-run" disabled={busy || !section.can_send} onClick={() => void send(false)}>
                    {busy ? "Working…" : "Send to client to sign"}
                  </button>
                  {askAddress && (
                    <button type="button" className="cf-btn cf-btn--secondary cf2-mark-done" disabled={busy} onClick={() => void send(true)}>
                      I have checked the address: send
                    </button>
                  )}
                </div>
              )}
              {line.key === "signature" && message && !(line.note && message.startsWith(line.note)) && (
                <p className="legal-aid-note" role="status">
                  {message}
                </p>
              )}
            </Line>
          ))
        )}
      </div>
    </>
  );
}
