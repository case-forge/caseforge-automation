
import { createHash, createPrivateKey, sign } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { canonical, FORMAT } from "../extension/answers.js";

export const LAB_KEY_ID = "lab-1";
const LAB_PHRASE = "caseforge portal fill lab key: not a secret, lab and tests only";
const PKCS8_ED25519_PREFIX = Buffer.from("302e020100300506032b657004220420", "hex");

export const keyFromSeed = (seed) => createPrivateKey({ key: Buffer.concat([PKCS8_ED25519_PREFIX, seed]), format: "der", type: "pkcs8" });
const labKey = () => keyFromSeed(createHash("sha256").update(LAB_PHRASE).digest());

export function signBody(body, { key = labKey(), keyId = LAB_KEY_ID } = {}) {
  const signature = sign(null, Buffer.from(canonical(body)), key).toString("base64url");
  return { format: FORMAT, key_id: keyId, signature, body };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const path = process.argv[2];
  if (!path) throw new Error("usage: node lab/sign.mjs <export.json>");
  const { body } = JSON.parse(await readFile(path, "utf8"));
  await writeFile(path, `${JSON.stringify(signBody(body), null, 2)}\n`);
}
