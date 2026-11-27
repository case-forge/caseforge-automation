
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  return Response.json({ name: editorFor(remoteUser), signed_in: Boolean(remoteUser) }, { headers: { "Cache-Control": "no-store" } });
}
