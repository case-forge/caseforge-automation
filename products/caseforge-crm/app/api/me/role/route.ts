
import { resolveCrmRole } from "@/lib/crmRole";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const { role, rejection } = await resolveCrmRole(request);
  if (rejection) return rejection;
  return Response.json({ role }, { headers: { "Cache-Control": "no-store" } });
}
