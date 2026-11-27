
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const MATTER = /^\d+$/;

function cleanChoices(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return out;
  for (const [key, value] of Object.entries(raw as Record<string, unknown>).slice(0, 40)) {
    if (typeof value === "string" && key.length <= 80) out[key] = value;
  }
  return out;
}

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const from = request.nextUrl.searchParams.get("from")?.trim() ?? "";
  const into = request.nextUrl.searchParams.get("into")?.trim() ?? "";
  if (!MATTER.test(from) || !MATTER.test(into)) {
    return Response.json({ error: "Both matter ids must be matter numbers." }, { status: 400 });
  }
  if (isStubMode()) {
    return Response.json({
      from: { matter_id: from, client_name: "Stub Alpha" },
      into: { matter_id: into, client_name: "Stub Beta" },
      refusals: [],
      moves: [{ label: "Hearings", table: "matter_hearings", move: 1, stay: 0 }],
      folder: {},
      choices: {
        fills: [{ id: "fill:people.phone_primary#1", column: "people.phone_primary", party: false, new: "07700 900123" }],
        conflicts: [
          { id: "people.dob_iso", column: "people.dob_iso", a: "1990-04-16", b: "1990-03-15", choice: "b" },
          { id: "matter_parties.email_primary#9", column: "matter_parties.email_primary", a: "alpha@example.com", b: "beta@example.com", choice: "b" },
        ],
        second_applicants: [],
      },
    });
  }
  return hubGetJson(request, "/client-viewer/clients/merge-preview", { from_matter_id: from, into_matter_id: into }, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const text = (key: string) => String(payload[key] ?? "").trim();
  const body = {
    from_matter_id: text("from_matter_id"),
    into_matter_id: text("into_matter_id"),
    typed_from: text("typed_from"),
    typed_into: text("typed_into"),
    reason: text("reason"),
    by: editorFor(remoteUser),
  };
  const choices = cleanChoices(payload.choices);
  if (!MATTER.test(body.from_matter_id) || !MATTER.test(body.into_matter_id)) {
    return Response.json({ error: "Both matter ids must be matter numbers." }, { status: 400 });
  }
  if (!body.typed_from || !body.typed_into) return Response.json({ error: "Type both clients' names to confirm." }, { status: 400 });
  if (body.reason.length < 3) return Response.json({ error: "Say why these clients are being merged." }, { status: 400 });
  if (isStubMode()) return Response.json({ merged: true });
  return hubPostJson(request, "/client-viewer/clients/merge", Object.keys(choices).length ? { ...body, choices } : body, remoteUser);
}
