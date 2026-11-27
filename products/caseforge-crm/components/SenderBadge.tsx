
import { senderInitials, senderLogoSrc } from "@/lib/specialSenderRules";
import type { SpecialSender } from "@/lib/specialSenderRules";
import { IconLandmark } from "./icons";

export function SpecialSenderBadge({ sender }: { sender: SpecialSender }) {
  const src = senderLogoSrc(sender);
  if (src) {
    return (
      <span className="sender-badge sender-badge--logo" title={sender.name} role="img" aria-label={sender.name}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" width={22} height={22} />
      </span>
    );
  }
  if (sender.mark) {
    const mark = sender.mark;
    return (
      <span className={`sender-badge sender-badge--mark sender-badge--letters${mark.text.length}`} style={{ background: mark.background }} title={sender.name} role="img" aria-label={sender.name}>
        {[...mark.text].map((letter, i) => (
          <span key={i} aria-hidden="true" style={{ color: mark.colours[i] }}>
            {letter}
          </span>
        ))}
      </span>
    );
  }
  return (
    <span className="sender-badge" title={sender.name} role="img" aria-label={sender.name}>
      <span aria-hidden="true">{senderInitials(sender.name)}</span>
    </span>
  );
}

export function CourtBadge() {
  return (
    <span className="sender-badge court-sender-badge" title="Court" role="img" aria-label="Court">
      <IconLandmark className="court-sender-badge-icon" aria-hidden="true" />
    </span>
  );
}
