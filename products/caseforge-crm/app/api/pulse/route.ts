
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stubFlagCounts } from "@/lib/stub";
import { stubUserFor } from "@/lib/stubUser";
import { stubAttention } from "@/lib/stubAttention";
import { stubRobotNotices } from "@/lib/stubRobot";
import { stubStatementReplies } from "@/lib/stubStatementReplies";
import { stubPendingCounts } from "@/lib/stubPendingNewClients";
import { stubNotifications } from "@/lib/stubNotifications";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  if (isStubMode()) {
    return Response.json({
      attention: stubAttention(),
      flag_counts: { counts: stubFlagCounts(["flagged", "starred"], stubUserFor(request, remoteUser)) },
      robot_notices: stubRobotNotices(),
      statement_replies: stubStatementReplies(),
      pending_new_clients: stubPendingCounts(),
      notifications: stubNotifications(),
      errors: [],
    });
  }
  return hubGetJson(request, "/client-viewer/pulse", {}, remoteUser);
}
