
export interface SenderMark {
  text: string;
  colours: string[];
  background: string;
}

export interface SpecialSender {
  id: string;
  name: string;
  domains: string[];
  new_clients: boolean;

  logo: string;

  mark: SenderMark | null;
}

const HEX = /^#[0-9a-fA-F]{6}$/;
export const MAX_MARK_LETTERS = 3;

export function parseMark(raw: unknown): SenderMark | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const text = typeof o.text === "string" ? o.text : "";
  const colours = Array.isArray(o.colours) ? o.colours : [];
  if (!/^[A-Za-z0-9]{1,3}$/.test(text) || colours.length !== text.length) return null;
  if (!colours.every((c) => typeof c === "string" && HEX.test(c)) || typeof o.background !== "string" || !HEX.test(o.background)) return null;
  return { text, colours: colours as string[], background: o.background };
}

export function parseSpecialSenders(raw: unknown): SpecialSender[] {
  const items = raw && typeof raw === "object" && Array.isArray((raw as { items?: unknown }).items) ? ((raw as { items: unknown[] }).items) : [];
  const out: SpecialSender[] = [];
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    if (typeof o.id !== "string" || typeof o.name !== "string" || !o.id || !o.name) continue;
    out.push({
      id: o.id,
      name: o.name,
      domains: Array.isArray(o.domains) ? o.domains.filter((d): d is string => typeof d === "string") : [],
      new_clients: o.new_clients === true,
      logo: typeof o.logo === "string" && /^[0-9a-f]{1,64}$|^stub$/.test(o.logo) ? o.logo : "",
      mark: parseMark(o.mark),
    });
  }
  return out;
}

export function domainMatches(senderDomain: string | undefined, domains: string[]): boolean {
  const d = (senderDomain ?? "").trim().toLowerCase();
  if (!d) return false;
  return domains.some((raw) => {
    const wanted = raw.trim().toLowerCase();
    return wanted !== "" && (d === wanted || d.endsWith(`.${wanted}`));
  });
}

export function matchSender(senders: SpecialSender[], input: { senderDomain?: string; newClient?: boolean }): { sender: SpecialSender; rank: number } | null {
  for (let rank = 0; rank < senders.length; rank++) {
    const sender = senders[rank];
    if (domainMatches(input.senderDomain, sender.domains) || (input.newClient === true && sender.new_clients)) return { sender, rank };
  }
  return null;
}

export function senderLogoSrc(sender: Pick<SpecialSender, "id" | "logo">): string {
  return sender.logo ? `/api/settings/special-sender-logo?id=${encodeURIComponent(sender.id)}&v=${encodeURIComponent(sender.logo)}` : "";
}

export function senderInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words.slice(0, 2).map((w) => w[0]) : [...(words[0] ?? "?")].slice(0, 2);
  return letters.join("").toLocaleUpperCase("en-GB");
}
