
export type CallerTag = { code: string; label: string; kind: "client" | "opponent" };

const CALLER_TAGS: { flag: string; tag: CallerTag }[] = [
  { flag: "persistent_caller", tag: { code: "PC", label: "Frequent caller", kind: "client" } },
  { flag: "persistent_caller_respondent", tag: { code: "PC(R)", label: "Frequent caller (Opponent)", kind: "opponent" } },
];

export function callerTagsOf(flags: Record<string, boolean> | null | undefined): CallerTag[] {
  if (!flags) return [];
  return CALLER_TAGS.filter(({ flag }) => flags[flag] === true).map(({ tag }) => tag);
}
