
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ALLOWED_ORIGINS, canonical, FORMAT, MAX_LIFETIME_MS, originAllowed, pageFor, parseExport, pathMatches } from "../extension/answers.js";
import { LAB_KEYS } from "../extension/lab-keys.js";
import { TRUSTED_KEYS } from "../extension/trusted-keys.js";
import { LAB_KEY_ID, signBody } from "../lab/sign.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const NOW = Date.parse("2026-11-11T10:00:00Z");
const iso = (ms) => new Date(ms).toISOString().replace(".000Z", "Z");

const throwaway = () => {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  return { privateKey, x: publicKey.export({ format: "jwk" }).x };
};
const body = (over = {}) => ({
  client: { reference: "101", surname: "Testperson" },
  contains_c8: false,
  expires: iso(NOW + 15 * 60 * 1000),
  format: FORMAT,
  issued: iso(NOW),
  matter_id: "101",
  page_must_show: "",
  pages: { "/steps/applicant/privacy_known/:id": [{ name: "x[y]", type: "radio", value: "no" }] },
  ...over,
});
const prod = () => {
  const { privateKey, x } = throwaway();
  return { keys: { production: { "prod-1": x }, lab: {} }, sign: (b, keyId = "prod-1") => JSON.stringify(signBody(b, { key: privateKey, keyId })) };
};

test("a correctly signed, unexpired export is accepted as production", async () => {
  const { keys, sign } = prod();
  const result = await parseExport(sign(body()), NOW, keys);
  assert.equal(result.error, undefined);
  assert.equal(result.trust, "production");
  assert.equal(result.data.matter_id, "101");
});

test("an unsigned export is refused", async () => {
  const { keys } = prod();
  assert.match((await parseExport(JSON.stringify(body()), NOW, keys)).error, /not an answers export this version reads/);
  assert.match((await parseExport(JSON.stringify({ format: FORMAT, body: body() }), NOW, keys)).error, /not signed/);
});

test("a tampered export is refused, whichever part was changed", async () => {
  const { keys, sign } = prod();
  const envelope = JSON.parse(sign(body()));
  const edits = [
    (e) => (e.body.expires = iso(NOW + 5 * 60 * 60 * 1000)),
    (e) => (e.body.client.reference = "999"),
    (e) => (e.body.matter_id = "102"),
    (e) => (e.body.contains_c8 = true),
    (e) => (e.body.pages["/steps/applicant/privacy_known/:id"][0].value = "yes"),
    (e) => (e.body.nonce = "added"),
  ];
  for (const edit of edits) {
    const forged = JSON.parse(JSON.stringify(envelope));
    edit(forged);
    assert.match((await parseExport(JSON.stringify(forged), NOW, keys)).error, /signature does not check out/);
  }
  const flipped = JSON.parse(JSON.stringify(envelope));
  flipped.signature = (flipped.signature[0] === "A" ? "B" : "A") + flipped.signature.slice(1);
  assert.match((await parseExport(JSON.stringify(flipped), NOW, keys)).error, /signature does not check out/);
  const junk = { ...envelope, signature: "not-a-signature" };
  assert.match((await parseExport(JSON.stringify(junk), NOW, keys)).error, /signature does not check out/);
});

test("an export signed by the wrong key, or an unknown key id, is refused", async () => {
  const { keys } = prod();
  const other = throwaway();
  const wrongKey = JSON.stringify(signBody(body(), { key: other.privateKey, keyId: "prod-1" }));
  assert.match((await parseExport(wrongKey, NOW, keys)).error, /signature does not check out/);
  const unknownId = JSON.stringify(signBody(body(), { key: other.privateKey, keyId: "prod-2" }));
  assert.match((await parseExport(unknownId, NOW, keys)).error, /key this extension does not know/);
  for (const id of ["__proto__", "constructor", "toString"]) {
    assert.match((await parseExport(JSON.stringify(signBody(body(), { key: other.privateKey, keyId: id })), NOW, keys)).error, /does not know/);
  }
});

test("an expired export is refused, and so is one that lasts over an hour or is issued in the future", async () => {
  const { keys, sign } = prod();
  assert.match((await parseExport(sign(body({ expires: iso(NOW - 1000) })), NOW, keys)).error, /expired/);
  assert.match((await parseExport(sign(body({ expires: iso(NOW) })), NOW, keys)).error, /expired/);
  const long = body({ issued: iso(NOW), expires: iso(NOW + MAX_LIFETIME_MS + 1000) });
  assert.match((await parseExport(sign(long), NOW, keys)).error, /longer than an hour/);
  assert.equal((await parseExport(sign(body({ expires: iso(NOW + MAX_LIFETIME_MS) })), NOW, keys)).error, undefined);
  const future = body({ issued: iso(NOW + 30 * 60 * 1000), expires: iso(NOW + 40 * 60 * 1000) });
  assert.match((await parseExport(sign(future), NOW, keys)).error, /issue time/);
  assert.match((await parseExport(sign(body({ issued: undefined })), NOW, keys)).error, /issue time/);
});

test("a signed body that is incomplete is still refused", async () => {
  const { keys, sign } = prod();
  assert.match((await parseExport(sign(body({ client: {} })), NOW, keys)).error, /which client/);
  assert.match((await parseExport(sign(body({ pages: {} })), NOW, keys)).error, /holds no answers/);
  assert.match((await parseExport(sign(body({ contains_c8: undefined })), NOW, keys)).error, /whether it holds C8/);
  assert.match((await parseExport(sign(body({ format: "other" })), NOW, keys)).error, /not an answers export this version reads/);
  assert.match((await parseExport("not json", NOW, keys)).error, /not an answers export/);
});

test("the shipped production key list holds no lab key, and the lab list is separate", () => {
  const lab = new Set([...Object.keys(LAB_KEYS), ...Object.values(LAB_KEYS)]);
  for (const [id, key] of Object.entries(TRUSTED_KEYS)) {
    assert.ok(!lab.has(id) && !lab.has(key), `production list holds a lab key: ${id}`);
    assert.match(key, /^[A-Za-z0-9_-]{43}$/, "a production key is a raw 32-byte Ed25519 key, base64url");
  }
  assert.ok(Object.keys(LAB_KEYS).every((id) => id.startsWith("lab-")));
});

test("with no production key installed the shipped extension refuses even a lab-signed export on the production list", async () => {
  const lab = JSON.stringify(signBody(body()));
  const shipped = await parseExport(lab, NOW);
  assert.equal(shipped.trust, "lab", "the lab key is trusted, as a lab key");
  assert.equal((await parseExport(lab, NOW, { production: TRUSTED_KEYS, lab: {} })).error?.includes("does not know"), true);
});

test("a lab-signed export fills lab addresses only and is not held to the one-hour cap", async () => {
  const lab = await parseExport(JSON.stringify(signBody(body({ expires: "2099-01-01T00:00:00Z" }))), NOW);
  assert.equal(lab.error, undefined);
  assert.equal(lab.trust, "lab");
  assert.equal(originAllowed("http://127.0.0.1:3000", "lab"), true);
  assert.equal(originAllowed("https://live.example", "lab", ["https://live.example"], ["http://127.0.0.1:3000"]), false);
  assert.equal(originAllowed("https://live.example", "production", ["https://live.example"], ["http://127.0.0.1:3000"]), true);
  assert.deepEqual(ALLOWED_ORIGINS, ["http://127.0.0.1:8377", "http://127.0.0.1:3000"]);
});

test("the sample export is signed by the lab key and its signature is current", async () => {
  const sample = await readFile(join(root, "lab/c100-sample-export.json"), "utf8");
  const result = await parseExport(sample, NOW);
  assert.equal(result.error, undefined);
  assert.equal(result.trust, "lab");
  assert.equal(JSON.parse(sample).key_id, LAB_KEY_ID);
  assert.equal(result.data.contains_c8, true);
  const edited = JSON.parse(sample);
  edited.body.contains_c8 = false;
  assert.match((await parseExport(JSON.stringify(edited), NOW)).error, /signature does not check out/);
});

test("a segment written :id in a page key stands for exactly one segment", () => {
  assert.equal(pathMatches("/steps/applicant/refuge/:id", "/steps/applicant/refuge/abc-123"), true);
  assert.equal(pathMatches("/steps/applicant/refuge/:id", "/steps/applicant/refuge/"), false);
  assert.equal(pathMatches("/steps/applicant/refuge/:id", "/steps/applicant/refuge/a/b"), false);
  assert.equal(pathMatches("/steps/applicant/refuge/:id", "/steps/respondent/refuge/abc"), false);
  const data = { pages: { "/steps/applicant/refuge/:id": [] } };
  assert.equal(pageFor(data, "http://127.0.0.1:3000/steps/applicant/refuge/abc", "lab").name, "/steps/applicant/refuge/:id");
  assert.match(pageFor(data, "https://live.example/steps/applicant/refuge/abc", "lab").error, /not a page this tool fills/);
});

test("the bytes signed are the same in the extension and in the hub's Python signer", async () => {
  assert.equal(canonical({ b: [1, true, null], a: "é\n", c: { z: 1, y: "\u0001" } }), '{"a":"é\\n","b":[1,true,null],"c":{"y":"\\u0001","z":1}}');
  const script = [
    "import sys, json, datetime as dt, base64",
    `sys.path.insert(0, ${JSON.stringify(join(root, "../../tools"))})`,
    "from vergil import portal_answers as pa",
    "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey",
    "key = Ed25519PrivateKey.generate()",
    "env = {pa.KEY_ENV: base64.b64encode(key.private_bytes_raw()).decode(), pa.KEY_ID_ENV: 'py-1'}",
    "pa.write_audit = lambda row: None",
    "record = {'name_last': 'Testperson', 'dob_iso': '1990-02-03', 'sex': 'Female', 'email_primary': 'café@example.invalid', 'address_line1': '1 Test Road', 'has_c8': '1', 'c8_email': '1'}",
    "made = pa.generate('101', requested_by='test', record=record, env=env)",
    "print(json.dumps({'export': made['export'], 'public': pa.public_key_b64u(key)}))",
  ].join("\n");
  const run = spawnSync("python3", ["-c", script], { encoding: "utf8" });
  if (run.status !== 0) return void console.log(`skipped: python3 with the hub's modules is not available here (${run.stderr.split("\n").at(-2)})`);
  const { export: made, public: publicKey } = JSON.parse(run.stdout);
  const result = await parseExport(JSON.stringify(made), Date.now(), { production: { "py-1": publicKey }, lab: {} });
  assert.equal(result.error, undefined);
  assert.equal(result.data.contains_c8, true);
  assert.equal(result.data.pages["/steps/applicant/contact_details/:id"].find((f) => f.name.endsWith("[email]")).value, "café@example.invalid");
});
