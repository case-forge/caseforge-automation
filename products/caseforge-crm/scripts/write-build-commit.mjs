
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const dist = path.join(process.cwd(), process.env.CASEFORGE_NEXT_DIST_DIR || ".next");
let commit = "unknown";
try {
  const out = execFileSync("git", ["rev-parse", "HEAD"], { stdio: ["ignore", "pipe", "ignore"] }).toString().trim();
  if (/^[0-9a-f]{40}$/.test(out)) commit = out;
} catch {

}
try {
  mkdirSync(dist, { recursive: true });
  writeFileSync(path.join(dist, "COMMIT"), `${commit}\n`);
} catch (err) {
  console.warn(`write-build-commit: could not write COMMIT (${err instanceof Error ? err.message : err})`);
}
