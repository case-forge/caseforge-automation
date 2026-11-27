import { IconPhoneRinging } from "./icons";
import { callerTagsOf, type CallerTag } from "@/lib/callerTags";

export function CallerTagBadge({ tag, className = "" }: { tag: CallerTag; className?: string }) {
  return (
    <span className={`caller-icon caller-icon--${tag.kind} ${className}`.trim()} role="img" title={tag.label} aria-label={tag.label}>
      <IconPhoneRinging className="caller-icon-svg" />
    </span>
  );
}

export function CallerIcons({ flags }: { flags: Record<string, boolean> | null | undefined }) {
  const tags = callerTagsOf(flags);
  if (tags.length === 0) return null;
  return (
    <span className="caller-icons">
      {tags.map((tag) => (
        <CallerTagBadge key={tag.code} tag={tag} />
      ))}
    </span>
  );
}
