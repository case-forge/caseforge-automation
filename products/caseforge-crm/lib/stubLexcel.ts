
import { LEXCEL_KINDS } from "./lexcelTypes";
import type { Lexcel, LexcelKind, LexcelLetter, LexcelMakeResult } from "./lexcelTypes";

const WORDS: Record<LexcelKind, { label: string; button: string }> = {
  opening: { label: "Opening client care letter", button: "Make the opening client care letter" },
  mid: { label: "Court outcome letter", button: "Make the court outcome letter" },
  closing: { label: "Closing letter", button: "Make the closing letter" },
};
const SEEDED: Record<string, LexcelKind[]> = { "9002": ["opening"], "9003": ["opening", "mid", "closing"] };

const REFUSES_OPENING = "9001";
const OPENING_REFUSAL = "Not made: the referral is 9.0 days old, over the 7-day safe-to-send window.";
const OPENING_OFFER = { key: "force", label: "Make it anyway: skip the 7-day referral check" };

const LOCKED_OPENING: Record<string, string> = { "9003": "The client has signed the opening client care letter in Documenso, so it is not made again." };

const HEARD: Record<string, string> = { "9002": "1 October 2026" };

interface Made {
  made_utc: string;
  made_by: string;
  made_via: string;
  times: number;
}

const states = new Map<string, Map<LexcelKind, Made>>();
const emailed = new Set<string>();

function stateFor(matterId: string): Map<LexcelKind, Made> {
  let s = states.get(matterId);
  if (!s) {
    s = new Map();
    (SEEDED[matterId] ?? []).forEach((kind, i) => {
      s!.set(kind, { made_utc: new Date(Date.UTC(2026, 9, 2 + i * 3, 10, 0)).toISOString(), made_by: "auto", made_via: "Case flow", times: 1 });
    });
    states.set(matterId, s);
  }
  return s;
}

function midNext(matterId: string, made: boolean): { can_make: boolean; note: string } {
  const day = HEARD[matterId];
  if (!day) return { can_make: !made, note: made ? "Every hearing that has happened has its letter." : "" };
  if (!made) return { can_make: true, note: `Generate makes the letter for the hearing on ${day}.` };
  if (!emailed.has(matterId)) return { can_make: true, note: `Generate drafts the email for the letter about the hearing on ${day}.` };
  return { can_make: false, note: "Every hearing that has happened has its letter." };
}

function letter(matterId: string, kind: LexcelKind): LexcelLetter {
  const made = stateFor(matterId).get(kind);
  const next = kind === "mid" ? midNext(matterId, made !== undefined) : { can_make: made === undefined, note: "" };
  return {
    kind,
    ...WORDS[kind],
    made: made !== undefined,
    made_utc: made?.made_utc ?? "",
    made_by: made?.made_by ?? "",
    made_via: made?.made_via ?? "",
    times: made?.times ?? 0,
    summary: made ? `${WORDS[kind].label} saved in the client's folder. Nothing was sent.` : "",
    links: made ? [{ label: "Open the letter in SharePoint", url: `https://example.invalid/stub/lexcel/${matterId}/${kind}` }] : [],
    ...next,
    ...(kind === "opening" && made && LOCKED_OPENING[matterId] ? { locked: LOCKED_OPENING[matterId] } : {}),
  };
}

export function stubLexcel(matterId: string): Lexcel {
  return { matter_id: matterId, letters: LEXCEL_KINDS.map((kind) => letter(matterId, kind)) };
}

export function stubMakeLexcel(matterId: string, kind: string, by: string, variant = ""): LexcelMakeResult | { error: string } {
  if (!LEXCEL_KINDS.includes(kind as LexcelKind)) return { error: "say which letter: opening, mid or closing" };
  if (!by.trim()) return { error: "type your name first" };
  const s = stateFor(matterId);
  const k = kind as LexcelKind;
  const before = s.get(k);
  const refused = (message: string, offers: LexcelMakeResult["offers"] = []): LexcelMakeResult => ({ ok: false, message, offers, links: [], lexcel: stubLexcel(matterId) });
  const regenerate = variant === "regenerate";
  if (variant && !regenerate && !(k === "opening" && variant === OPENING_OFFER.key)) return { error: "that is not a choice this letter offers" };
  if (regenerate && before && k !== "mid") {
    if (k === "opening" && LOCKED_OPENING[matterId]) return refused(`Not made: ${LOCKED_OPENING[matterId]}`);
    s.set(k, { made_utc: new Date().toISOString(), made_by: by.trim(), made_via: "Lexcel", times: before.times + 1 });
    const name = k === "opening" ? "Client Care Letter - Opening - STUB (regenerated).docx" : `${WORDS[k].label} (regenerated).docx`;
    return {
      ok: true,
      message: `New ${WORDS[k].label.toLowerCase()} saved beside the earlier one, as ${name}; Documenso envelope made; email drafted, marked AI DRAFTED. Nothing was sent. The earlier letter, envelope and draft are left as they are.`,
      offers: [],
      links: [{ label: "Open the draft in Outlook", url: `https://example.invalid/stub/lexcel/${matterId}/${k}-again` }],
      lexcel: stubLexcel(matterId),
    };
  }
  if (before && k !== "mid") {

    return refused(`${WORDS[k].label}: one already exists. Nothing was made.`);
  }
  if (k === "opening" && matterId === REFUSES_OPENING && variant !== OPENING_OFFER.key) return refused(OPENING_REFUSAL, [OPENING_OFFER]);
  if (k === "mid" && !HEARD[matterId] && !before) return refused("No hearing is waiting for an outcome letter.");
  if (k === "mid" && before && HEARD[matterId] && !emailed.has(matterId)) {
    emailed.add(matterId);
    return {
      ok: true,
      message: `Email to the client with the outcome letter for the hearing on ${HEARD[matterId]} drafted. Nothing was sent.`,
      offers: [],
      links: [{ label: "Open the draft in Outlook", url: `https://example.invalid/stub/lexcel/${matterId}/mid-email` }],
      lexcel: stubLexcel(matterId),
    };
  }
  if (k === "mid" && before) return refused("No hearing is waiting for an outcome letter.");
  s.set(k, { made_utc: new Date().toISOString(), made_by: by.trim(), made_via: "Lexcel", times: (before?.times ?? 0) + 1 });
  const made = letter(matterId, k);
  return {
    ok: true,
    message: `${WORDS[k].label} saved in the client's folder. Nothing was sent. Billed as one routine letter out.`,
    offers: [],
    links: made.links,
    lexcel: stubLexcel(matterId),
  };
}
