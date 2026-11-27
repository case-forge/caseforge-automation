
import { proxyGame } from "@/lib/gameProxy";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

async function handle(request: Request, ctx: Ctx): Promise<Response> {
  return proxyGame(request, (await ctx.params).path);
}

export const GET = handle;
export const HEAD = handle;
export const POST = handle;
