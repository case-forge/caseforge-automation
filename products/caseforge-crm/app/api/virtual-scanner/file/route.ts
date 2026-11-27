
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { fileResponse, hubGetFile, isStubMode } from "@/lib/hubProxy";
import { stubPdf } from "@/lib/stubVirtualScanner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const documentId = (request.nextUrl.searchParams.get("document_id") ?? "").trim();
  if (!documentId) return Response.json({ error: "document_id is required" }, { status: 400 });
  if (documentId.startsWith("t:")) return Response.json({ error: "There is no stock copy of this document yet." }, { status: 404 });
  if (isStubMode()) {
    return fileResponse(stubPdf() as BodyInit, { contentType: "application/pdf", disposition: 'inline; filename="stub.pdf"', fallbackFilename: "stub.pdf" });
  }
  return hubGetFile(request, "/client-viewer/virtual-scanner/file", { document_id: documentId }, remoteUser, "document.pdf");
}
