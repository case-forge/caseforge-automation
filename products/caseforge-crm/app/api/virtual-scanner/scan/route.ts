
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { asText, hubPostJson, isStubMode, readJsonObject } from "@/lib/hubProxy";
import { stubScan } from "@/lib/stubVirtualScanner";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const payload = await readJsonObject(request);
  if (!payload) return Response.json({ error: "malformed request body" }, { status: 400 });
  const matterId = asText(payload.matter_id);
  const documentId = asText(payload.document_id);
  const date = asText(payload.date_received);
  const by = editorFor(remoteUser);
  const copies = Number(payload.copies ?? 1);
  if (!Number.isInteger(copies) || copies < 1 || copies > 20) return Response.json({ error: "Copies must be a whole number from 1 to 20." }, { status: 400 });
  if (!/^\d+$/.test(matterId) || !documentId) return Response.json({ error: "matter_id and document_id are required" }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return Response.json({ error: "Give the date the document came in." }, { status: 400 });
  if (isStubMode()) {
    const result = stubScan(matterId, documentId, date, by, copies);
    return "error" in result ? Response.json(result, { status: 422 }) : Response.json(result);
  }
  return hubPostJson(request, "/client-viewer/virtual-scanner/scan", { matter_id: matterId, document_id: documentId, date_received: date, by, copies }, remoteUser);
}
