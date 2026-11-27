
export const ROLE_CHOICES = ["Applicant", "Respondent", "Other"] as const;
export type RoleChoice = (typeof ROLE_CHOICES)[number];

export const OTHER_PARTY_ROLE = "Other party";

export function roleChoiceOf(role: string): RoleChoice | "" {
  const r = role.trim().toLowerCase();
  if (!r) return "";
  if (r === "applicant") return "Applicant";
  if (r === "respondent") return "Respondent";
  return "Other";
}

export function roleOtherTextOf(role: string): string {
  return roleChoiceOf(role) === "Other" ? role : "";
}

export function roleToStore(role: string): string {
  return role.trim() || OTHER_PARTY_ROLE;
}
