"use client";

import { FIRM_LINKS, isTailnetOnly, logoSrc } from "@/lib/firmLinks";

export function FirmLinksPanel() {
  return (
    <ul className="firm-links-list">
      {FIRM_LINKS.map((link) => (
        <li key={link.href}>
          <a className="firm-link" href={link.href} target="_blank" rel="noopener noreferrer">
            {!link.logo ? (
              <span className="firm-link-icon firm-link-icon--chip firm-link-icon--letter" aria-hidden="true">{link.label.charAt(0)}</span>
            ) : link.mono ? (
              <span className="firm-link-icon firm-link-icon--mono" style={{ maskImage: `url(${logoSrc(link)})`, WebkitMaskImage: `url(${logoSrc(link)})` }} aria-hidden="true" />
            ) : (
              <span className="firm-link-icon firm-link-icon--chip" aria-hidden="true">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={logoSrc(link)} alt="" width={24} height={24} />
              </span>
            )}
            <span className="firm-link-text">
              <span className="firm-link-label">{link.label}</span>
              <span className="firm-link-desc">{link.description}</span>
              {isTailnetOnly(link.href) && <span className="firm-link-tailnet">Tailnet only</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
