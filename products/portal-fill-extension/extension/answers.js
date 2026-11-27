
import { LAB_KEYS } from "./lab-keys.js";
import { TRUSTED_KEYS } from "./trusted-keys.js";

export const FORMAT = "caseforge-portal-answers/2";
export const IDLE_MS = 15 * 60 * 1000;

export const MAX_LIFETIME_MS = 60 * 60 * 1000;
const SKEW_MS = 2 * 60 * 1000;

export const ALLOWED_ORIGINS = ["http://127.0.0.1:8377", "http://127.0.0.1:3000"];

export const LAB_ORIGINS = ["http://127.0.0.1:8377", "http://127.0.0.1:3000"];

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).filter((key) => value[key] !== undefined).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function unbase64url(text) {
  const plain = String(text).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(plain + "=".repeat((4 - (plain.length % 4)) % 4));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

export async function signatureValid(publicKey, signature, bytes) {
  try {
    const key = await crypto.subtle.importKey("raw", unbase64url(publicKey), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify({ name: "Ed25519" }, key, unbase64url(signature), bytes);
  } catch {
    return false;
  }
}

export async function parseExport(text, now = Date.now(), keys = { production: TRUSTED_KEYS, lab: LAB_KEYS }) {
  let envelope;
  try {
    envelope = JSON.parse(text);
  } catch {
    return { error: "That is not an answers export. Copy it again from the client's page." };
  }
  if (!envelope || envelope.format !== FORMAT || typeof envelope.body !== "object" || !envelope.body) {
    return { error: "That is not an answers export this version reads." };
  }
  const { key_id: keyId, signature, body } = envelope;
  if (typeof signature !== "string" || typeof keyId !== "string") return { error: "This export is not signed, so it is refused." };
  const own = (list) => (Object.prototype.hasOwnProperty.call(list, keyId) ? list[keyId] : null);
  const production = own(keys.production);
  const lab = production ? null : own(keys.lab);
  if (!production && !lab) return { error: "This export was signed with a key this extension does not know, so it is refused." };
  if (!(await signatureValid(production || lab, signature, new TextEncoder().encode(canonical(body))))) {
    return { error: "This export's signature does not check out, so it is refused. Make a new one from the client's page." };
  }
  const trust = production ? "production" : "lab";
  if (body.format !== FORMAT) return { error: "That is not an answers export this version reads." };
  if (!body.client || !body.client.surname || !body.client.reference) return { error: "The export does not say which client it is for." };
  if (!body.pages || typeof body.pages !== "object" || !Object.keys(body.pages).length) return { error: "The export holds no answers." };
  if (typeof body.contains_c8 !== "boolean") return { error: "The export does not say whether it holds C8 contact details." };
  const expires = Date.parse(body.expires);
  const issued = Date.parse(body.issued);
  if (!Number.isFinite(expires)) return { error: "The export has no expiry time." };
  if (expires <= now) return { error: "This export has expired. Make a new one from the client's page." };
  if (trust === "production") {
    if (!Number.isFinite(issued) || issued > now + SKEW_MS) return { error: "The export has no valid issue time, so it is refused." };
    if (expires - issued > MAX_LIFETIME_MS) return { error: "This export lasts longer than an hour, so it is refused." };
  }
  return { data: body, trust };
}

export function originAllowed(origin, trust = "production", allowed = ALLOWED_ORIGINS, lab = LAB_ORIGINS) {
  return allowed.includes(origin) && (trust !== "lab" || lab.includes(origin));
}

export function pathMatches(key, pathname) {
  const want = key.split("/");
  const have = pathname.split("/");
  return want.length === have.length && want.every((part, at) => (part === ":id" ? have[at].length > 0 : part === have[at]));
}

export function pageFor(data, url, trust = "production") {
  let address;
  try {
    address = new URL(url);
  } catch {
    return { error: "This tab is not a page this tool fills." };
  }
  if (!originAllowed(address.origin, trust)) return { error: "This tab is not a page this tool fills." };
  const name = Object.keys(data.pages).find((key) => (key.startsWith("/") ? pathMatches(key, address.pathname) : address.href.endsWith(`/${key}`)));
  return name ? { name, fields: data.pages[name] } : { error: "The export has no answers for this page." };
}

export async function load() {
  const { held } = await chrome.storage.session.get("held");
  if (!held) return null;
  if (Date.now() - held.touched > IDLE_MS || Date.parse(held.data.expires) <= Date.now()) {
    await clear();
    return null;
  }
  return held;
}

export async function keep(data, confirmed = false, trust = "production") {

  await chrome.storage.session.set({ held: { data, confirmed, trust, touched: Date.now() } });
}

export async function clear() {
  await chrome.storage.session.clear();
}

export const ARRANGEMENTS = {
  waitingRoom: "a separate waiting room in the court building",
  entrance: "a separate entrance and exit from the court building",
  screen: "to be shielded by a privacy screen in the courtroom",
  video: "to join the hearing by video link rather than in person",
};

export function specialArrangementsFields(keys) {
  const unknown = keys.filter((key) => !(key in ARRANGEMENTS));
  if (unknown.length) throw new Error(`Unknown arrangement: ${unknown.join(", ")}`);
  const chosen = Object.keys(ARRANGEMENTS).filter((key) => keys.includes(key));
  if (!chosen.length) return [{ id: "isSpecialArrangementsRequired", type: "yesno", value: "No" }];
  return [
    { id: "isSpecialArrangementsRequired", type: "yesno", value: "Yes" },
    { id: "specialArrangementsRequired", type: "textarea", value: chosen.map((key) => ARRANGEMENTS[key]).join("\n"), conditional: true },
  ];
}
