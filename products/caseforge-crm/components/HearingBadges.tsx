import { hearingMarkers, isCounselBooked, isUnlinked, isVacated, requestLabel } from "@/lib/hearings";
import type { Hearing } from "@/lib/hearings";
import { IconAlert } from "./icons";

const EX_PARTE_RE = /\bex[- ]?parte\b|\bwithout\s+notice\b/i;

export function isExParte(hearing: Pick<Hearing, "hearing_type" | "notes" | "notice">): boolean {
  return hearing.notice === "without notice" || EX_PARTE_RE.test(`${hearing.hearing_type ?? ""} ${hearing.notes ?? ""}`);
}

export function HearingBadges({ hearing, markers = false }: { hearing: Hearing; markers?: boolean }) {
  const badges: { key: string; className: string; label: string; short?: string; icon?: boolean }[] = [];
  if (isVacated(hearing)) badges.push({ key: "vacated", className: "hearing-badge hearing-badge--muted", label: hearing.replaced_by ? "Vacated - moved" : "Vacated", short: "Vacated" });

  const requested = requestLabel(hearing);
  if (requested) badges.push({ key: "request", className: "hearing-badge hearing-badge--request", label: requested, icon: true });
  if (hearing.is_final && hearing.status === "scheduled") badges.push({ key: "final", className: "hearing-badge hearing-badge--final", label: "Final" });

  if (isExParte(hearing)) badges.push({ key: "exparte", className: "hearing-badge hearing-badge--exparte", label: "Ex parte" });
  if (hearing.review_state === "needs_review") badges.push({ key: "review", className: "hearing-badge hearing-badge--review", label: "Review", icon: true });
  if (hearing.review_state !== "needs_review" && isCounselBooked(hearing)) {
    badges.push({ key: "counsel", className: "hearing-badge hearing-badge--counsel", label: "Counsel booked", short: "Counsel" });
  }

  if (isUnlinked(hearing)) {
    badges.push({ key: "unlinked", className: "hearing-badge hearing-badge--unlinked", label: "Not linked to a client", short: "No client" });
  }

  if (markers) for (const m of hearingMarkers(hearing)) badges.push({ key: m.key, className: "hearing-badge hearing-badge--review", label: m.label, short: m.short });
  if (badges.length === 0) return null;
  return (
    <>
      {badges.map((badge) => (
        <span key={badge.key} className={badge.className}>
          {badge.icon && <IconAlert className="hearing-badge-icon" aria-hidden="true" />}
          {badge.short ? (
            <>
              <span className="hearing-badge-full">{badge.label}</span>
              <span className="hearing-badge-short">{badge.short}</span>
            </>
          ) : (
            badge.label
          )}
        </span>
      ))}
    </>
  );
}
