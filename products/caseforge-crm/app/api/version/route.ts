
import { readFile } from "node:fs/promises";
import path from "node:path";
import { resolveAccessIdentity } from "@/lib/accessIdentity";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {

  const distDir = path.join(process.cwd(), process.env.CASEFORGE_BUILD_DIST_DIR || ".next");
  let buildId = "";
  try {
    buildId = (await readFile(path.join(distDir, "BUILD_ID"), "utf8")).trim();
  } catch {

  }

  let commit: string | null = null;
  try {
    const raw = (await readFile(path.join(distDir, "COMMIT"), "utf8")).trim();
    commit = /^[0-9a-f]{40}$/.test(raw) ? raw : null;
  } catch {

  }

  const identity = await resolveAccessIdentity(request.headers);
  const sessionExpiresAt =
    identity.kind === "identified" && typeof identity.exp === "number" ? identity.exp * 1000 : null;

  return Response.json({ buildId, commit, sessionExpiresAt });
}
