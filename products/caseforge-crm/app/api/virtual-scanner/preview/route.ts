
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { fileResponse, hubGetFile, isStubMode } from "@/lib/hubProxy";
import { stubPreviewSvg } from "@/lib/stubVirtualScanner";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  const documentId = (request.nextUrl.searchParams.get("document_id") ?? "").trim();
  if (!documentId) return Response.json({ error: "document_id is required" }, { status: 400 });
  if (documentId.startsWith("t:")) return Response.json({ error: "There is no stock copy of this document yet." }, { status: 404 });
  if (isStubMode()) {
    return fileResponse(stubPreviewSvg(), { contentType: "image/svg+xml", disposition: 'inline; filename="stub.svg"', fallbackFilename: "stub.svg" });
  }
  return hubGetFile(request, "/client-viewer/virtual-scanner/preview", { document_id: documentId }, remoteUser, "preview.jpg");
}
