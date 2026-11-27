
export const ORDER_ACRONYMS: readonly string[] = [
  "FL401",
  "FL403",
  "C100",
  "C1A",
  "C8",
  "NMO",
  "OO",
  "CAO",
  "PSO",
  "SIO",
  "DVPO",
  "LAA",
  "DV",
  "UK",
];

export const COURT_NAMES: readonly string[] = [
  "Kingston-Upon-Thames Family Court",
  "Newcastle upon Tyne Family Court",
  "Kingston-Upon-Hull Family Court",
  "Basingstoke Magistrates' Court",
  "Colchester Magistrates' Court",
  "Aldershot Magistrates' Court",
  "Gateshead Magistrates' Court",
  "St Helens Magistrates' Court",
  "Stockport Magistrates' Court",
  "Willesden Magistrates' Court",
  "Edmonton Magistrates' Court",
  "Stoke-on-Trent Family Court",
  "Worthing Magistrates' Court",
  "Bedford Magistrates' Court",
  "Middlesbrough Family Court",
  "Telford Magistrates' Court",
  "Wolverhampton Family Court",
  "Wrexham Magistrates' Court",
  "Huddersfield Family Court",
  "Medway Magistrates' Court",
  "Northampton Family Court",
  "Southampton Family Court",
  "Wigan Magistrates' Court",
  "Birkenhead County Court",
  "Birmingham Family Court",
  "Canterbury Family Court",
  "Chelmsford Family Court",
  "Manchester Family Court",
  "Nottingham Family Court",
  "Portsmouth Family Court",
  "Sunderland Family Court",
  "Doncaster Family Court",
  "Guildford Family Court",
  "Lancaster Family Court",
  "Leicester Family Court",
  "Liverpool Family Court",
  "Sheffield Family Court",
  "Worcester Family Court",
  "Bradford Family Court",
  "Coventry Family Court",
  "Bristol Family Court",
  "Cardiff Family Court",
  "Central Family Court",
  "Chester Family Court",
  "Ipswich Family Court",
  "Lincoln Family Court",
  "Newport Family Court",
  "Norwich Family Court",
  "Reading Family Court",
  "Swansea Family Court",
  "Taunton Family Court",
  "Barnet Family Court",
  "Exeter Family Court",
  "Oxford Family Court",
  "Slough Family Court",
  "Crewe Family Court",
  "Leeds Family Court",
  "Luton Family Court",
  "Truro Family Court",
  "York Family Court",
];

const COURT_SUFFIXES = [" Family Court", " Magistrates' Court", " County Court"];

const COURT_VENUES: readonly string[] = Array.from(
  new Set(
    COURT_NAMES.map((name) => {
      const suffix = COURT_SUFFIXES.find((s) => name.endsWith(s));
      return suffix ? name.slice(0, -suffix.length).trim() : "";
    }).filter(Boolean),
  ),
).sort((a, b) => b.length - a.length);

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function whole(word: string): string {
  return `(?<![A-Za-z0-9])${escapeRegExp(word)}(?![A-Za-z0-9])`;
}

export function isAllCaps(text: string): boolean {
  return /\p{L}/u.test(text) && !/\p{Ll}/u.test(text);
}

export function restoreAcronyms(text: string): string {
  let out = text;
  for (const acronym of ORDER_ACRONYMS) out = out.replace(new RegExp(whole(acronym), "gi"), acronym);
  return out;
}

export function normaliseOrderText(value: string | null | undefined): string {
  if (value == null) return "";
  const text = String(value);
  if (!text.trim()) return "";
  if (!isAllCaps(text)) return text;
  let out = text
    .trim()
    .toLowerCase()
    .replace(/(^|[.!?]\s+)(\p{L})/gu, (_m, lead: string, letter: string) => lead + letter.toUpperCase());
  out = restoreAcronyms(out);
  for (const name of COURT_NAMES) out = out.replace(new RegExp(whole(name), "gi"), () => name);
  out = out.replace(new RegExp(whole("family court"), "gi"), "Family Court");
  for (const venue of COURT_VENUES) {
    out = out.replace(
      new RegExp(`(\\b(?:court|sitting) at\\s+)${whole(venue)}`, "gi"),
      (_m, lead: string) => lead + venue,
    );
  }
  return out;
}
